# unreflectGetter() và unreflectSetter(): kiểm chứng quyền cùng giới hạn của field final

## 1. Mục tiêu và bối cảnh

Reflection cho phép tìm một `Field` từ tên class và tên field. Method Handle API còn cho phép chuyển `Field` đó thành một đối tượng gọi có kiểu: `MethodHandles.Lookup.unreflectGetter(Field)` tạo handle đọc giá trị, còn `unreflectSetter(Field)` tạo handle ghi giá trị. Cả hai đều rất hữu ích trong mapper, serializer, framework xử lý metadata và bộ chuyển đổi dữ liệu.

Nhưng có hai ranh giới phải kiểm tra kỹ:

1. **Quyền truy cập:** tìm được `Field` không có nghĩa được phép tạo getter/setter handle, đặc biệt khi field `private` hoặc class nằm trong package của một named module khác.
2. **Tính bất biến:** quyền đọc field `final` không kéo theo quyền sửa field đó. Những hạn chế với final instance fields còn được tăng cường từ JDK 26 theo JEP 500.

Bài thuộc chương **Lookup và adapter** của module `JAVA_VERSION_JAVA18`. Kiến thức tập trung vào các hợp đồng `MethodHandle`, `Lookup`, Reflection và module còn áp dụng trên JDK hiện đại, phù hợp với mục tiêu học kiểm chứng API ngay trên JDK đang chạy. Không xem việc thay đổi field `final` bằng deep reflection là một kỹ thuật lập trình bình thường.

Sau bài học, bạn có thể:

- Dự đoán `MethodType` của getter/setter cho field instance và static.
- Dùng `unreflectGetter()`, `unreflectSetter()` và `invokeExact()` cho field có thể truy cập hợp lệ.
- Phân biệt quyền tạo handle với quyền gọi handle và trạng thái `accessible` của đối tượng `Field`.
- Kiểm chứng giới hạn `private` và `opens`/`exports` trên named module.
- Phân biệt giới hạn của `final` instance field, `static final`, record field và hidden-class field.
- Hiểu chính sách JDK 26+ về final-field mutation và không dựa vào hành vi vốn sẽ bị siết chặt.
- Chọn `findGetter`/`findSetter`, `unreflectVarHandle` hoặc accessor public khi phù hợp.
- Viết kiểm thử ghi nhận rõ `IllegalAccessException` và `WrongMethodTypeException`.

## 2. unreflectGetter() và unreflectSetter() làm gì?

Hai phương thức nằm trong `java.lang.invoke.MethodHandles.Lookup`:

~~~java
MethodHandle getter = lookup.unreflectGetter(field);
MethodHandle setter = lookup.unreflectSetter(field);
~~~

Trong đó:

- `field` là một `java.lang.reflect.Field` đã được tìm thấy.
- `lookup` là `MethodHandles.Lookup` đại diện cho quyền truy cập của lookup class.
- `getter` và `setter` là `MethodHandle` có chữ ký cố định, mô tả bằng `MethodType`.
- Cả hai phương thức có thể ném `IllegalAccessException` ngay tại **thời điểm tạo handle** khi quyền truy cập không đáp ứng hợp đồng.
- Nếu field là `final`, việc tạo setter còn chịu các giới hạn riêng của `Field.set(...)` và chính sách final-field mutation hiện đại.

Điểm khác so với `Field.get`/`Field.set`: MethodHandle là một **capability** đã được tạo sau khi kiểm tra quyền. Sau khi caller có tham chiếu đến handle, lời gọi qua handle không lặp lại kiểm tra quyền truy cập của `Lookup` theo từng lần `invokeExact`. Vì vậy, **không phát tán handle tới code không đáng tin cậy** nếu handle cho phép truy cập member không công khai.

### Getter/setter không phải method Java được khai báo trong source

`unreflectGetter`/`unreflectSetter` không yêu cầu class có những phương thức tên `getX()` hoặc `setX()`. Chúng tham chiếu trực tiếp đến field thực tế đã xác định bởi `Field`.

Ví dụ, nếu một class có field `int counter` thì bạn có thể tạo một getter handle dù class **không khai báo** phương thức `getCounter()`. Đây là quyền đọc trực tiếp field, không phải JavaBeans property accessor.

## 3. Kiểu của MethodHandle: instance và static

Giả sử class `C` chứa field kiểu `T`. MethodType phụ thuộc vào việc field có phải static hay không.

| Field | Getter handle | Setter handle |
| --- | --- | --- |
| `T C.field` (instance) | `(C)T` | `(C,T)void` |
| `static T C.field` | `()T` | `(T)void` |

Với một field instance, getter cần **receiver** thuộc class khai báo field (hoặc subtype phù hợp); setter cần receiver và giá trị cần ghi. Với field static, cả hai handle **không cần receiver**.

Ví dụ chữ ký mong đợi:

~~~text
Sample.count    : int      -> getter (Sample)int, setter (Sample,int)void
Sample.global   : int      -> getter ()int,       setter (int)void
Sample.memo     : String   -> getter (Sample)String, setter (Sample,String)void
~~~

Bạn có thể kiểm chứng bằng `MethodHandle.type()`, hoặc so sánh với `MethodType.methodType(...)`.

### invokeExact có hợp đồng kiểu chặt chẽ

Với handle kiểu `(Sample)int`, lời gọi hợp lệ là:

~~~java
int count = (int) getter.invokeExact(sample);
~~~

Lời gọi sau không tương đương:

~~~java
// Ví dụ sai về chữ ký call site:
Object count = getter.invokeExact(sample);
~~~

`invokeExact` đòi descriptor của call site khớp **chính xác** với `handle.type()`. Gọi bằng return type `Object` thay vì `int` sẽ dẫn đến `WrongMethodTypeException`; với `invoke` thường có các chuyển đổi được phép theo cơ chế `asType`. Không được cho rằng mọi chuyển đổi tự xảy ra như `Field.get(...)` hoặc `Field.set(...)`.

## 4. Ví dụ có thể chạy: field instance và static có quyền truy cập

Tạo tệp `FieldHandleLab.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Field;

public class FieldHandleLab {
    public static final class Sample {
        public int count = 7;
        public static int global = 2;

        private String memo = "demo";

        // Final fields chỉ phục vụ minh họa quyền đọc và giới hạn setter.
        public final long id = 123L;
        public static final int VERSION = 3;
    }

    public record Receipt(int code) {
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup ownLookup = MethodHandles.lookup();
        Sample sample = new Sample();

        // Instance field: (Sample)int và (Sample,int)void
        Field countField = Sample.class.getDeclaredField("count");
        MethodHandle getCount = ownLookup.unreflectGetter(countField);
        MethodHandle setCount = ownLookup.unreflectSetter(countField);

        assertType(getCount, MethodType.methodType(int.class, Sample.class));
        assertType(setCount,
                MethodType.methodType(void.class, Sample.class, int.class));

        int before = (int) getCount.invokeExact(sample);
        setCount.invokeExact(sample, 11);
        int after = (int) getCount.invokeExact(sample);

        System.out.println("count: " + before + " -> " + after);

        // Static field: ()int và (int)void
        Field globalField = Sample.class.getDeclaredField("global");
        MethodHandle getGlobal = ownLookup.unreflectGetter(globalField);
        MethodHandle setGlobal = ownLookup.unreflectSetter(globalField);

        assertType(getGlobal, MethodType.methodType(int.class));
        assertType(setGlobal, MethodType.methodType(void.class, int.class));

        int oldGlobal = (int) getGlobal.invokeExact();
        setGlobal.invokeExact(9);
        int newGlobal = (int) getGlobal.invokeExact();

        System.out.println("global: " + oldGlobal + " -> " + newGlobal);

        // Hai class là nestmate: lookup từ class ngoài có thể thấy
        // private field của class lồng bên trong.
        Field memoField = Sample.class.getDeclaredField("memo");

        try {
            MethodHandles.publicLookup().unreflectGetter(memoField);
            throw new AssertionError("Expected a private access failure");
        } catch (IllegalAccessException expected) {
            System.out.println("publicLookup cannot read private memo");
        }

        MethodHandle getMemo = ownLookup.unreflectGetter(memoField);
        MethodHandle setMemo = ownLookup.unreflectSetter(memoField);

        String oldMemo = (String) getMemo.invokeExact(sample);
        setMemo.invokeExact(sample, "updated");
        String newMemo = (String) getMemo.invokeExact(sample);

        System.out.println("memo: " + oldMemo + " -> " + newMemo);

        // Đọc final field được khi có quyền truy cập phù hợp.
        Field idField = Sample.class.getDeclaredField("id");
        MethodHandle getId = ownLookup.unreflectGetter(idField);
        long id = (long) getId.invokeExact(sample);
        System.out.println("id (read-only): " + id);

        // Không bật accessible hay xin quyền sửa final field.
        // Setter thông thường cho final field không được cấp.
        expectSetterRejected(ownLookup, idField);

        // Static final không thể có setter qua unreflectSetter.
        Field versionField = Sample.class.getDeclaredField("VERSION");
        expectSetterRejected(ownLookup, versionField);

        // Record component field là private final: không được ghi.
        Field recordField = Receipt.class.getDeclaredField("code");
        MethodHandle getCode = ownLookup.unreflectGetter(recordField);
        Receipt receipt = new Receipt(55);
        int code = (int) getCode.invokeExact(receipt);
        System.out.println("record code: " + code);
        expectSetterRejected(ownLookup, recordField);
    }

    private static void assertType(MethodHandle handle, MethodType expected) {
        if (!handle.type().equals(expected)) {
            throw new AssertionError(
                    "Expected " + expected + ", got " + handle.type());
        }
    }

    private static void expectSetterRejected(
            MethodHandles.Lookup lookup,
            Field field) throws Exception {

        try {
            lookup.unreflectSetter(field);
            throw new AssertionError(
                    "Unexpected writable final field: " + field);
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "Setter rejected: "
                            + field.getDeclaringClass().getSimpleName()
                            + "." + field.getName());
        }
    }
}
~~~

Chạy trên JDK mục tiêu:

~~~sh
javac FieldHandleLab.java
java FieldHandleLab
~~~

Đầu ra điển hình:

~~~text
count: 7 -> 11
global: 2 -> 9
publicLookup cannot read private memo
memo: demo -> updated
id (read-only): 123
Setter rejected: Sample.id
Setter rejected: Sample.VERSION
record code: 55
Setter rejected: Receipt.code
~~~

Những điểm cần chú ý:

1. `Sample` được khai báo `public static` và nằm trong một public outer class, nên `publicLookup()` có thể dùng những public member đủ điều kiện. Nhưng `memo` là private nên phép tạo getter bằng public lookup bị từ chối.
2. `MethodHandles.lookup()` gọi từ `FieldHandleLab` có quyền private đối với nestmate `Sample`; điều này **không đồng nghĩa** mọi lookup đều có quyền với private field ở class khác.
3. `id`, `VERSION` và `Receipt.code` được đọc thành công khi có quyền, nhưng code **không cố bật `setAccessible(true)` cho final field**. Setter mặc định bị từ chối.
4. Trong một chương trình đã biên dịch có thể có các tối ưu hóa với `static final` hằng; đọc field bằng handle không đồng nghĩa được phép sửa hằng.
5. Kết quả cụ thể phụ thuộc đúng source, compiler và phiên bản runtime; nếu thay đổi các điều kiện truy cập hoặc cơ chế mutation, hãy phân tích lại theo hợp đồng API thay vì chỉ nhìn thông báo.

## 5. Khám phá Field khác với có quyền tạo handle

Một đoạn code có thể tìm thấy private field:

~~~java
Field secret = SomeType.class.getDeclaredField("secret");
~~~

Nhưng câu lệnh này **chỉ là discovery**, không phải cấp quyền. Khi gọi:

~~~java
MethodHandle getter = MethodHandles.lookup().unreflectGetter(secret);
~~~

nếu `secret` không được truy cập bởi lookup class theo quy tắc Java/JPMS, phép unreflect có thể ném `IllegalAccessException`.

### Thời điểm kiểm tra quyền

Hợp đồng `Lookup.unreflectGetter(Field)` và `Lookup.unreflectSetter(Field)` nêu:

- Nếu `Field` **chưa** được bật accessible flag, quyền được kiểm tra **ngay khi tạo handle**, thay mặt lookup class.
- Nếu `Field` **đã** được bật accessible flag hợp pháp, cơ chế suppress Java language access checks của đối tượng `Field` được tính đến khi unreflect.
- Việc bật accessible flag **không cho phép** vi phạm mọi giới hạn `final`; khả năng ghi final là một điều kiện riêng.
- Sau khi được tạo hợp lệ, handle mang quyền sử dụng member tương ứng. Không chia sẻ private getter/setter cho code không được tin cậy.

Ví dụ thử quyền một cách rõ ràng:

~~~java
Field field = Account.class.getDeclaredField("memo");

boolean enabled = field.trySetAccessible();
if (!enabled) {
    throw new IllegalStateException(
            "Package containing Account is not open to this caller");
}

MethodHandle getter =
        MethodHandles.lookup().unreflectGetter(field);
~~~

Đoạn trên chỉ hợp lệ nếu caller **thực sự được phép** bật accessible flag. Trên named modules khác nhau, thư viện cần `opens` package tương ứng cho module caller; `exports` public API thường **không đủ** để truy cập sâu vào private member.

### trySetAccessible không hứa có setter cho final

`field.trySetAccessible() == true` chỉ nói rằng có thể suppress kiểm tra Java language access trong các điều kiện được phép. Với `final`, phải xét **thêm** hợp đồng `Field.set` và final-field-mutation policy. Không viết code theo giả định “accessible thành công thì unreflectSetter chắc chắn thành công”.

## 6. exports, opens và Lookup trong named modules

Giả sử có hai named module:

~~~text
src/
├── demo.model/
│   ├── module-info.java
│   └── demo/model/Account.java
└── demo.consumer/
    ├── module-info.java
    └── demo/consumer/Main.java
~~~

### Module cung cấp class

`src/demo.model/module-info.java`:

~~~java
module demo.model {
    exports demo.model;
    opens demo.model to demo.consumer;
}
~~~

`src/demo.model/demo/model/Account.java`:

~~~java
package demo.model;

public final class Account {
    public int count = 1;
    private String memo = "sample";

    public String memo() {
        return memo;
    }
}
~~~

`exports demo.model;` công bố public API cho consumer. `opens demo.model to demo.consumer;` cho phép consumer dùng **deep reflection** vào những private member trong package này.

### Module tiêu thụ

`src/demo.consumer/module-info.java`:

~~~java
module demo.consumer {
    requires demo.model;
}
~~~

`src/demo.consumer/demo/consumer/Main.java`:

~~~java
package demo.consumer;

import demo.model.Account;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Throwable {
        Account account = new Account();
        MethodHandles.Lookup caller = MethodHandles.lookup();

        // Public field trong exported package.
        Field countField = Account.class.getDeclaredField("count");
        MethodHandle countGet = caller.unreflectGetter(countField);
        int count = (int) countGet.invokeExact(account);
        System.out.println("public count = " + count);

        // Discovery thấy private field, nhưng lookup thường từ module
        // consumer không tự có PRIVATE access với class Account.
        Field memo = Account.class.getDeclaredField("memo");
        try {
            caller.unreflectGetter(memo);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("Direct private getter lookup rejected");
        }

        // Cách 1: Field được mở accessible hợp pháp nhờ opens.
        if (!memo.trySetAccessible()) {
            throw new IllegalStateException("Package not opened");
        }
        MethodHandle getMemo = caller.unreflectGetter(memo);
        System.out.println((String) getMemo.invokeExact(account));

        // Cách 2: tạo Lookup có quyền private vào class đích.
        MethodHandles.Lookup privateLookup =
                MethodHandles.privateLookupIn(Account.class, caller);

        Field fresh = Account.class.getDeclaredField("memo");
        MethodHandle getWithPrivateLookup =
                privateLookup.unreflectGetter(fresh);
        MethodHandle setWithPrivateLookup =
                privateLookup.unreflectSetter(fresh);

        System.out.println((String) getWithPrivateLookup.invokeExact(account));
        setWithPrivateLookup.invokeExact(account, "updated by consumer");
        System.out.println(account.memo());
    }
}
~~~

Chạy từ thư mục gốc dự án:

~~~sh
javac -d mods --module-source-path src -m demo.model,demo.consumer
java --module-path mods -m demo.consumer/demo.consumer.Main
~~~

Đầu ra điển hình:

~~~text
public count = 1
Direct private getter lookup rejected
sample
sample
updated by consumer
~~~

### Thử loại bỏ opens

Đổi module descriptor thư viện thành:

~~~java
module demo.model {
    exports demo.model;
}
~~~

Biên dịch lại cả hai module và chạy lại:

- Đọc `count` bằng public getter handle vẫn hợp lệ.
- `caller.unreflectGetter(memo)` vẫn bị từ chối.
- `memo.trySetAccessible()` sẽ không cấp quyền deep reflection cho consumer.
- `privateLookupIn(Account.class, caller)` cũng không thành công vì package chưa được opened cho caller.

Tùy cấu trúc bài thử, lỗi xảy ra ở `trySetAccessible` hoặc `privateLookupIn`; không nên diễn giải `Class.getDeclaredField` tìm thành công là bằng chứng rằng đã được phép đọc field.

## 7. Trường hợp nào dùng findGetter/findSetter thay unreflect?

`Lookup` có hai nhóm API:

| Nhóm | Đầu vào | Phù hợp khi |
| --- | --- | --- |
| `unreflectGetter(Field)`, `unreflectSetter(Field)` | Đã có `Field` từ Reflection | Framework đang phân tích annotation, duyệt fields hoặc nhận đối tượng Field. |
| `findGetter(Class, String, Class)`, `findSetter(Class, String, Class)` | Biết class, tên field và kiểu field | Tạo handle trực tiếp mà không cần gọi `getDeclaredField` trước. |
| `findStaticGetter(...)`, `findStaticSetter(...)` | Class, tên và kiểu của static field | Cần field static cụ thể. |

Ví dụ public instance field:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle byName = lookup.findGetter(
        FieldHandleLab.Sample.class, "count", int.class);

MethodHandle byField = lookup.unreflectGetter(
        FieldHandleLab.Sample.class.getDeclaredField("count"));

System.out.println(byName.type());  // (Sample)int
System.out.println(byField.type()); // (Sample)int
~~~

Cả hai hướng đều cần quyền truy cập hợp lệ. `findSetter` không phải cách lách giới hạn của field `final`: phương thức tìm setter thông thường không cấp quyền ghi final field.

Với framework đã có `Field`, `unreflectGetter`/`unreflectSetter` giúp tránh lặp quá trình tra cứu field theo tên. Nhưng với code biết trước class và tên, `findGetter`/`findSetter` có thể thể hiện ý định rõ hơn. Không có bảo đảm hiệu năng một bên luôn nhanh hơn; chỉ so sánh bằng benchmark đúng workload.

## 8. final field: đọc được không có nghĩa ghi được

`final` biểu thị rằng field có hợp đồng khởi tạo/bất biến đặc biệt. Java compiler và JVM có thể dựa vào các giả định của final-field semantics. Thay đổi final field sau khi đối tượng đã được công bố có thể làm chương trình hành xử khó dự đoán, kể cả việc các vị trí đọc khác nhau quan sát các giá trị khác nhau.

Hãy phân loại:

| Loại field | Getter khi có quyền hợp lệ | Setter bằng unreflectSetter |
| --- | --- | --- |
| Instance non-final `int count` | Có | Có, khi được cấp quyền ghi tương ứng |
| Static non-final `static int global` | Có | Có, khi được cấp quyền ghi tương ứng |
| Instance final trong class thông thường | Có | Mặc định không; chỉ trong các điều kiện **rất hẹp** được `Field.set` và chính sách final-field mutation cho phép |
| `static final` | Có | **Không**, ngay cả khi gọi `setAccessible(true)` |
| Final field của record | Có nếu có quyền đọc | **Không** |
| Final field của hidden class | Có nếu có quyền đọc | **Không** |

### static final: không có ngoại lệ ghi qua unreflectSetter

Với:

~~~java
public static final String PROTOCOL = "v1";
~~~

`unreflectGetter` có thể đọc khi caller có quyền. Nhưng `unreflectSetter` không được phép tạo writable handle cho field vừa `static` vừa `final`. Gọi `setAccessible(true)` không làm field này trở nên writable.

### Record và hidden-class final fields

Record component được biểu diễn bằng final instance field bên trong record. Những final field này thuộc nhóm không cho phép ghi lại qua deep reflection, dù bạn có thể truy cập để đọc khi được cấp quyền hợp lệ.

Tương tự, final field khai báo trong hidden class cũng không có quyền ghi theo ngoại lệ dành cho ordinary final instance fields. Không nên sử dụng bytecode trick hoặc API không công khai để vòng qua ranh giới đó.

### Vì sao ordinary instance final vẫn được nhắc tới như một ngoại lệ?

Tài liệu `Lookup.unreflectSetter` nói setter cho final field bị chặn **trừ một số tình huống hẹp** tương ứng với `Field.set`. Trước đây, cơ chế này chủ yếu phục vụ deserialization/reconstruction. Nhưng **không phải hợp đồng chung cho phép sửa `final` sau khi khởi tạo**.

Ngay cả khi một JDK cho phép tạo setter handle trong tình huống đặc biệt, việc thay đổi giá trị final sau khi object đã được dùng có thể vi phạm các giả định tối ưu hóa và tính bất biến. Thiết kế ứng dụng nên thay đổi dữ liệu qua constructor, factory, builder hoặc object mới, không qua final-field mutation.

## 9. JDK 26+ và JEP 500: final-field mutation đang bị siết chặt

**JEP 500 – Prepare to Make Final Mean Final**, được đưa vào JDK 26, bổ sung cảnh báo và tùy chọn runtime để hạn chế việc sửa final instance fields qua deep reflection. `MethodHandles.Lookup.unreflectSetter(Field)` nằm trong nhóm *mutation methods* chịu chính sách này.

Điểm quan trọng:

- Final-field mutation không chỉ phụ thuộc vào `setAccessible(true)`. Nó còn liên quan tới quyền của **module thực hiện mutation**, tính mở của package đích và loại field.
- Trên JDK 26, chế độ mặc định là phát cảnh báo đối với mutation không được cấp quyền riêng (`warn`). Một bản JDK tương lai có thể chuyển mặc định sang `deny`. **Luôn kiểm tra tài liệu và tùy chọn của JDK thực tế** thay vì giả định chế độ mặc định không thay đổi.
- Đối với `unreflectSetter`, sự kiện/cảnh báo có thể xảy ra ở bước **tạo writable handle** cho final field, không chỉ khi gọi handle.
- `--enable-final-field-mutation=...` là cơ chế cấp quyền dành cho trường hợp thật sự bắt buộc và phải thỏa những điều kiện truy cập bổ sung. Nó **không** cho phép sửa `static final`, record final hoặc hidden-class final.
- `--illegal-final-field-mutation=deny` hữu ích để kiểm tra ứng dụng có phụ thuộc vào hành vi mutation sắp bị hạn chế hay không, trên JDK hỗ trợ tùy chọn.

### Kiểm tra khả năng tương thích, không dùng làm cách lập trình mặc định

Trên JDK 26 hoặc JDK hỗ trợ các tùy chọn tương ứng, có thể chạy suite kiểm thử ứng dụng với:

~~~sh
java --illegal-final-field-mutation=deny -jar app.jar
~~~

Cách này giúp phát hiện dependency cố tạo writable setter cho ordinary final instance field khi không được cấp quyền phù hợp. Nếu chương trình chỉ **đọc** final field hoặc dùng các accessor công khai, nó không cần quyền final-field mutation.

Nếu một thư viện thực sự phụ thuộc vào deserialization/reconstruction theo cơ chế final-field mutation, hãy đọc JEP 500 và tài liệu migration của đúng JDK, cân nhắc thay thư viện hoặc đổi thiết kế trước. Không thêm `--enable-final-field-mutation=ALL-UNNAMED` một cách rộng rãi chỉ để che cảnh báo.

### Hai rào cản riêng: module opens và quyền mutation

Một package `opens p to m` cho phép module `m` **thử deep reflection** vào member không public. Nhưng `opens` **không tự cấp quyền sửa final field** theo JEP 500. Ngược lại, bật final-field-mutation cho một module cũng **không tự mở package** đang bị JPMS đóng.

Vì vậy, với ordinary final instance field trên JDK 26+, phải xét đồng thời:

1. Có thể bật accessible flag của Field hợp pháp hay không?
2. Field có thuộc nhóm cho phép ngoại lệ mutation không (non-static, class thường, không record/hidden)?
3. Module thực hiện mutation có được cấp quyền cần thiết hay không, hoặc runtime đang ở chính sách cảnh báo tạm thời?
4. Package khai báo field có quan hệ module phù hợp hay không?
5. Việc mutation có đúng tình huống hẹp như reconstruction trước khi object được công bố hay không?

Trong ứng dụng thông thường, câu trả lời nên là: **đừng tạo setter handle cho final field**.

## 10. unreflectVarHandle không giống unreflectSetter

`MethodHandles.Lookup.unreflectVarHandle(Field)` tạo một `VarHandle` chứ không phải MethodHandle. Nó khác `unreflectGetter`/`unreflectSetter` ở hai điểm rất dễ nhầm:

- `unreflectVarHandle` thực hiện kiểm tra quyền theo **lookup class**, **bất kể accessible flag của Field**. Không giả định `field.setAccessible(true)` sẽ làm unreflectVarHandle vượt các giới hạn này.
- VarHandle có các **access mode** như `get`, `set`, volatile, compare-and-set tùy theo loại field. Với final field, các mode ghi như `SET` không được hỗ trợ; getter vẫn có thể hợp lệ khi caller có quyền.

Ví dụ minh họa:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Field;

Field count = FieldHandleLab.Sample.class.getDeclaredField("count");

VarHandle variable =
        MethodHandles.lookup().unreflectVarHandle(count);

FieldHandleLab.Sample sample = new FieldHandleLab.Sample();
int current = (int) variable.get(sample);
variable.set(sample, current + 1);
~~~

`VarHandle` phù hợp cho các bài toán điều khiển truy cập biến và memory ordering; nó không phải đường tắt để ghi vào final field. Không dùng một benchmark `MethodHandle` rồi tự suy ra hiệu năng của `VarHandle`, vì hai API có dạng lời gọi và semantics khác nhau.

## 11. Kiểm thử quyền và giới hạn final theo ma trận

Hãy xây dựng kiểm thử theo **loại field** và **ngữ cảnh truy cập**, không chỉ kiểm thử một trường hợp “setter tạo được”.

| Bài kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Public instance non-final | Public type trong exported package | Getter/setter handle tạo được với lookup đủ quyền |
| Public static non-final | Public type trong exported package | Getter không có receiver; setter nhận một value |
| Private instance non-final, cùng nest | Lookup từ nestmate có private access | Getter/setter tạo và gọi được |
| Private instance non-final, module khác chưa mở package | Caller lookup không đủ quyền | Unreflect thất bại với `IllegalAccessException` |
| Private instance non-final, package opened và `Field.trySetAccessible()` thành công | Module được cấp quyền | Có thể tạo handle từ reflected Field |
| Ordinary final instance field, không bật accessible | Không dùng đặc quyền mutation | Getter có thể thành công; setter bị từ chối |
| Static final | Dù Field accessible được bật hợp pháp | Setter luôn bị từ chối |
| Record final | Kể cả khi có quyền đọc sâu | Setter bị từ chối |
| Hidden-class final | Kể cả khi có quyền đọc sâu | Setter bị từ chối |
| Ordinary final với chính sách `deny` | Không có quyền mutation bổ sung | Mutation/setter hợp lệ không được cấp |

Một số kiểm thử chỉ có ý nghĩa trên JDK hỗ trợ chính sách JEP 500. Không nhầm kết quả một phiên bản JDK cũ với hành vi bắt buộc của phiên bản mới.

### Ví dụ kiểm tra không vô tình tạo setter final

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

static MethodHandle writableHandle(
        MethodHandles.Lookup lookup,
        Field field) throws IllegalAccessException {

    if (Modifier.isFinal(field.getModifiers())) {
        throw new IllegalArgumentException(
                "Refuse to create setter for final field: " + field);
    }
    return lookup.unreflectSetter(field);
}
~~~

Đây là một **chính sách an toàn của ứng dụng**: từ chối mọi final field trước khi gọi `unreflectSetter`. Nó không cố tái hiện hết các ngoại lệ lịch sử hoặc chính sách runtime, nhưng dễ hiểu, ổn định và phù hợp với các chương trình không có nhu cầu reconstruction đặc biệt.

## 12. Các lỗi và ngoại lệ thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `NoSuchFieldException` | Sai tên field hoặc đang tìm declared/inherited nhầm | Kiểm tra `getDeclaredField`, `getField` và declaring class |
| `IllegalAccessException` khi tạo getter | Lookup không có quyền với field hoặc class/package | Kiểm tra visibility, module, `exports`/`opens` và accessible flag |
| `trySetAccessible() == false` | Package ở module khác không opened cho caller | Sửa module descriptor hoặc cung cấp public accessor |
| `IllegalAccessException` khi tạo setter final | Field không có quyền ghi theo `Field.set`/JDK policy | Không sửa final; dùng constructor, factory, record mới |
| `WrongMethodTypeException` tại `invokeExact` | Descriptor call site khác `MethodHandle.type()` | In `handle.type()` và sửa kiểu receiver/return/args |
| `ClassCastException` hoặc `NullPointerException` khi gọi handle | Receiver/value không hợp lệ hoặc receiver null | Kiểm tra dữ liệu đầu vào và kiểu |
| Getter static được gọi với receiver | Nhầm kiểu getter `()T` với instance `(C)T` | Kiểm tra `Modifier.isStatic` và `handle.type()` |
| Setter static final bị từ chối | Static final không writable qua `unreflectSetter` | Không dùng setAccessible để vòng qua |
| Cảnh báo JDK 26+ khi tạo writable final handle | JEP 500 final-field mutation policy | Loại bỏ final mutation hoặc kiểm tra dependency/JDK migration |
| `unreflectVarHandle` vẫn bị từ chối dù `Field` đã accessible | VarHandle lookup luôn kiểm tra quyền độc lập với accessible flag | Tạo Lookup hợp lệ, không coi `setAccessible` là quyền VarHandle |

### Kiểm tra quyền theo thứ tự

Khi gặp lỗi, ưu tiên kiểm tra:

1. Field có tồn tại và đúng declaring class không?
2. Field là instance hay static? Kiểu field có khớp MethodType không?
3. Field có `final` không? Nếu có, hãy cân nhắc bỏ đường setter trước tiên.
4. Lookup được tạo từ class/module nào? Có quyền access phù hợp không?
5. Nếu vượt ranh giới named modules, package có exported cho public access hoặc opened cho deep reflection không?
6. Accessible flag của Field đã bật hợp lệ hay chưa?
7. Với final instance field, có chính sách final-field mutation nào áp dụng trên JDK đó không?
8. Có để lộ handle có quyền private cho code không tin cậy không?

## 13. Thiết kế thực tế: ưu tiên accessor và bất biến

Trong ứng dụng nghiệp vụ thông thường, lựa chọn nên ưu tiên:

1. **API công khai hoặc package API được thiết kế rõ ràng:** getter, constructor, factory, builder, cập nhật qua method có kiểm tra invariant.
2. **MethodHandle getter/setter cho non-final field khi thật sự cần framework access:** lookup và quyền cấp hẹp, chuẩn bị handle một lần rồi cache hợp lý.
3. **VarHandle khi cần memory-ordering semantics:** chỉ với field và access mode hỗ trợ hợp lệ.
4. **Reflection chỉ đọc final field nếu được cấp quyền:** không biến việc đọc thành quyền ghi ngầm định.
5. **Không mutate final để “tối ưu” hoặc sửa object đã công bố:** có thể làm hỏng invariant, security, và các giả định của JIT.

Ví dụ, với record:

~~~java
record User(int id, String name) {
}

User original = new User(7, "An");
User renamed = new User(original.id(), "Binh");
~~~

Tạo object mới là cách diễn đạt rõ ràng hơn việc tìm field private final rồi cố tạo writable handle.

Với lớp bất biến thường:

~~~java
final class Config {
    private final int timeoutSeconds;

    Config(int timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }

    Config withTimeoutSeconds(int next) {
        return new Config(next);
    }
}
~~~

Đây là hợp đồng dễ bảo trì và ít phụ thuộc vào chi tiết JDK hơn so với final-field mutation qua Reflection.

## 14. Bài tập thực hành

### Bài tập 1: Dự đoán MethodType

Với các field sau:

~~~java
class Types {
    String name;
    static long counter;
    boolean active;
}
~~~

Hãy viết chữ ký MethodType của getter và setter cho từng field. Sau đó dùng `unreflectGetter`/`unreflectSetter` để xác minh bằng `handle.type()`.

### Bài tập 2: So sánh hai lookup

Chạy `FieldHandleLab`. Dùng `MethodHandles.publicLookup()` tìm getter cho `Sample.memo` rồi dùng `MethodHandles.lookup()` từ nestmate. Giải thích vì sao một lookup thất bại và lookup còn lại thành công.

### Bài tập 3: Kiểm chứng JPMS

Biên dịch ví dụ hai module. Đầu tiên giữ `opens demo.model to demo.consumer;`, rồi bỏ directive đó. Quan sát `trySetAccessible()`, `unreflectGetter()` và `privateLookupIn()`. Giải thích sự khác nhau giữa public export và deep reflection.

### Bài tập 4: Final-field matrix

Viết test cho ordinary final instance field, static final field và record component field. Trước tiên chỉ tạo getter, sau đó xác nhận chính sách ứng dụng từ chối setter. Không mutate các field này.

### Bài tập 5: Kiểm tra JDK 26+ migration

Nếu JDK đang dùng có hỗ trợ, chạy suite test với `--illegal-final-field-mutation=deny`. Xác định dependency nào còn cố tạo writable setter cho final field. Viết giải pháp thay thế không phụ thuộc vào final-field mutation.

### Bài tập 6: unreflectVarHandle

Từ cùng `Field` mutable, tạo MethodHandle getter/setter và VarHandle; so sánh quyền truy cập, dạng lời gọi và các access mode. Thử với final field, xác định những mode nào không được hỗ trợ.

### Bài tập 7: Thiết kế mapper an toàn

Một mapper dùng Reflection quét `Field` rồi tạo accessor cache. Thiết kế chính sách:

- Field non-final: có thể tạo setter khi đủ quyền.
- Field final: chỉ đọc hoặc khởi tạo qua constructor/factory.
- Private field từ module khác: yêu cầu public API hoặc qualified `opens` phù hợp.
- Không trả private handle cho plugin không đáng tin.
- Cache phân biệt class loader, field name, field type và loại accessor.

Giải thích vì sao chính sách này ổn định hơn cách gọi `setAccessible(true)` cho tất cả fields.

## 15. Ghi nhớ

- **`unreflectGetter(Field)` tạo MethodHandle đọc; `unreflectSetter(Field)` tạo MethodHandle ghi.** Chữ ký của handle phụ thuộc instance/static và kiểu field.
- **Tìm được `Field` chưa phải quyền truy cập.** Nếu accessible flag chưa bật, Lookup kiểm tra quyền ngay khi tạo handle.
- **`invokeExact` yêu cầu kiểu chính xác.** Với instance field có receiver; với static field không có receiver.
- **Accessible flag và quyền ghi final là hai điều kiện khác nhau.** `trySetAccessible()` thành công không bảo đảm unreflectSetter cho final.
- **`static final`, record final và hidden-class final không thể có setter hợp lệ qua `unreflectSetter`.**
- **Ordinary final instance field chỉ có ngoại lệ mutation rất hẹp và đang bị siết chặt.** Từ JDK 26, JEP 500 bổ sung cảnh báo/chính sách riêng; không dựa vào mutation như thiết kế ứng dụng.
- **`opens` cho phép deep reflection nhưng không tự cấp quyền final-field mutation.** `exports` cũng không cho phép đọc private field trong module khác chỉ nhờ public API access.
- **`unreflectVarHandle` kiểm tra quyền của Lookup độc lập với accessible flag.** VarHandle cũng không phải cách vòng qua final.
- **Ưu tiên constructor, factory, builder và public API** để bảo toàn invariant và quyền truy cập trên JDK hiện đại.

## Tài liệu chính thống

- [Oracle Java SE 26 — MethodHandles.Lookup: unreflectGetter, unreflectSetter, unreflectVarHandle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Oracle Java SE 26 — Field: setAccessible, Field.set và final-field limitations](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html).
- [Oracle Java SE 26 — AccessibleObject: trySetAccessible và canAccess](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [Oracle Java SE 26 — Mutation methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html).
- [OpenJDK — JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500).
- [Oracle JDK 26 Migration Guide — Preparing for Final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html).
- [Oracle Java SE 26 — MethodHandle.invokeExact](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Oracle Java SE 26 — VarHandle API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html).

