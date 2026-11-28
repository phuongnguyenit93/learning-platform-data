# Private member trong cùng nest và trường hợp kiểm tra quyền khác giữa các lớp gọi

## 1. Mục tiêu bài học

Bài thuộc chương **Quyền reflection** của mô-đun **JAVA_VERSION_JAVA18**. Mô-đun nghiên cứu những hành vi Java 18 vẫn hữu ích trên JDK hiện đại, gồm UTF-8 mặc định, simple web server, Javadoc snippet và cách kiểm chứng hợp đồng API liên quan đến phân giải tên, reflection và `MethodHandle`. Ở đây ta tập trung vào trường hợp một lớp đọc hoặc gọi được private member bằng reflection, nhưng một lớp gọi khác lại bị từ chối.

Quy tắc **nest-based access control** được đưa vào từ Java 11 và vẫn áp dụng trên JDK 18 trở lên. Quy tắc này cho phép các lớp thuộc **cùng một nest** truy cập private member của nhau theo cơ chế kiểm tra quyền Java. Nó không có nghĩa mọi lớp cùng package đều có quyền private.

Sau bài học, bạn có thể:

- Phân biệt **cùng nest**, **cùng package**, **cùng tệp nguồn** và **cùng module**.
- Dùng `Class.getNestHost()`, `Class.getNestMembers()` và `Class.isNestmateOf(Class<?>)` để quan sát nest theo JVM.
- Phân biệt tìm metadata (`getDeclaredField`/`getDeclaredMethod`), kiểm tra quyền (`canAccess`) và thực hiện reflective access (`Field.get`/`Method.invoke`).
- Giải thích vì sao một private member có thể truy cập được từ caller này nhưng bị từ chối từ caller khác.
- Hiểu giới hạn của `trySetAccessible` khi bật cơ chế bỏ qua kiểm tra truy cập, đặc biệt xuyên named modules.
- Phân loại chính xác các ngoại lệ truy cập, lỗi tìm metadata và lỗi của thân phương thức.

## 2. Khái niệm nest: quan hệ của các lớp, không phải tên package

Xét một top-level class có hai nested classes:

```java
public class Document {
    private String title = "Draft";

    static class Reader {
        static String read(Document document) {
            return document.title;
        }
    }

    static class Writer {
        static void update(Document document) {
            document.title = "Published";
        }
    }
}
```

`Document` là *nest host*, còn `Document.Reader` và `Document.Writer` là các *nestmates*. Trong trường hợp mã nguồn như trên, cả ba đều thuộc cùng một nest, nên `Reader` và `Writer` có thể truy cập trường `private title` theo kiểm tra quyền ngôn ngữ.

```text
Nest host: Document
  |
  +-- Document
  +-- Document$Reader  <-- cùng nest -->  Document$Writer

IndependentReader (top-level, dù cùng package)
  |
  +-- nest khác: không tự có quyền đọc private của Document
```

Kiểm chứng qua runtime:

```java
System.out.println(
        Document.Reader.class.getNestHost() == Document.class); // true
System.out.println(
        Document.Reader.class.isNestmateOf(Document.Writer.class)); // true
System.out.println(
        Document.Reader.class.isNestmateOf(Document.class)); // true
```

Bạn cũng có thể khảo sát `Document.class.getNestMembers()`. Không suy luận quyền truy cập chỉ từ dấu `$` trong tên bytecode hoặc từ việc hai class nằm trong cùng tệp `.java`: quan hệ nest là dữ liệu runtime được JVM xác định. Hai top-level classes riêng biệt vẫn thuộc các nest riêng, kể cả khi đặt cùng package.

**Ranh giới lịch sử:** Đây là tính năng Java 11 còn hữu ích trên JDK hiện đại; không nên mô tả nó là tính năng lần đầu xuất hiện từ Java 18.

## 3. Tìm thấy private member không đồng nghĩa có quyền gọi

Một phép thử reflection có ba công đoạn:

1. **Tìm metadata:** `Vault.class.getDeclaredField("secret")` tìm trường được khai báo trực tiếp trong `Vault`, kể cả trường private. `getDeclaredMethod("reveal")` làm việc tương tự với phương thức và đúng danh sách kiểu tham số.
2. **Kiểm tra quyền ở caller hiện tại:** `field.canAccess(vault)` hoặc `method.canAccess(vault)` xét quyền reflective access theo ngữ cảnh lớp gọi, cùng trạng thái bỏ qua kiểm tra truy cập của đối tượng reflection.
3. **Thực hiện:** `field.get(vault)` hoặc `method.invoke(vault)` đọc/gọi thực tế, có thể ném `IllegalAccessException` nếu caller không có quyền.

| API | Câu hỏi trả lời | Không thể kết luận |
| --- | --- | --- |
| `getDeclaredField("secret")` | Lớp khai báo trường tên `secret` không? | Có thể đọc giá trị trường không |
| `getDeclaredMethod("reveal")` | Có khai báo phương thức đúng tên/chữ ký không? | Có thể gọi phương thức không |
| `field.canAccess(vault)` | Caller **đang thực hiện kiểm tra** có quyền không? | Caller khác chắc chắn có cùng kết quả |
| `field.get(vault)` | Đọc giá trị có thành công không? | Caller khác cũng đọc được |
| `method.invoke(vault)` | Gọi method có thành công không? | Mọi lỗi phát sinh đều là lỗi quyền truy cập |
| `trySetAccessible()` | Có thể bật chế độ bỏ qua kiểm tra truy cập không? | Bật được từ mọi module trong mọi trường hợp |

`AccessibleObject.canAccess(Object)` có phụ thuộc caller; các điểm gọi trong **lớp khác nhau** có thể cho kết quả khác nhau dù dùng cùng kiểu target. Khi gọi `canAccess` với instance field hoặc instance method, phải truyền receiver hợp lệ; với static member và constructor, giá trị dùng để kiểm tra là `null`. Truyền receiver sai có thể ném `IllegalArgumentException`.

**Điểm cần quan sát:** Một hàm tiện ích nằm bên trong nest của target có thể đọc private member và trả kết quả cho một class bên ngoài. Điều đó **không chứng minh** class bên ngoài tự nó có quyền gọi `Field.get`. Quyền được kiểm tra tại lớp nơi lời gọi reflection thực sự diễn ra.

## 4. Ví dụ đầy đủ: cùng nest và khác nest, dù cùng package

Đây là ví dụ tự chứa có thể biên dịch bằng JDK 18 hoặc mới hơn. Hai lớp lồng nhau `NestAccessDemo.Vault` và `NestAccessDemo.NestReader` cùng nest; top-level class `IndependentReader` được viết trong **cùng tệp nguồn** nhưng ở nest khác. Cả hai đều nhận cùng một đối tượng `Vault` và tìm đúng hai private members.

Lưu thành **`NestAccessDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class NestAccessDemo {
    public static final class Vault {
        private final String secret = "sample-value";

        private String reveal() {
            return "revealed:" + secret;
        }
    }

    public static final class NestReader {
        public static void inspect(Vault vault) throws Exception {
            Field field = Vault.class.getDeclaredField("secret");
            Method method = Vault.class.getDeclaredMethod("reveal");

            System.out.println("nest.field.canAccess="
                    + field.canAccess(vault));
            System.out.println("nest.method.canAccess="
                    + method.canAccess(vault));

            // Caller là nestmate, không cần trySetAccessible().
            System.out.println("nest.field.value=" + field.get(vault));
            System.out.println("nest.method.value=" + method.invoke(vault));
        }
    }

    public static void main(String[] args) throws Exception {
        Vault vault = new Vault();

        System.out.println("nest.host="
                + Vault.class.getNestHost().getSimpleName());
        System.out.println("same.nest="
                + Vault.class.isNestmateOf(NestReader.class));
        System.out.println("other.nest="
                + Vault.class.isNestmateOf(IndependentReader.class));

        NestReader.inspect(vault);
        IndependentReader.inspect(vault);
        IndependentReader.inspectAfterOverride(vault);
    }
}

// Top-level class khác nest, mặc dù cùng tệp nguồn và package.
class IndependentReader {
    static void inspect(NestAccessDemo.Vault vault) throws Exception {
        Field field = NestAccessDemo.Vault.class
                .getDeclaredField("secret");
        Method method = NestAccessDemo.Vault.class
                .getDeclaredMethod("reveal");

        System.out.println("other.field.canAccess="
                + field.canAccess(vault));
        System.out.println("other.method.canAccess="
                + method.canAccess(vault));

        try {
            field.get(vault);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("other.field=IllegalAccessException");
        }

        try {
            method.invoke(vault);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("other.method=IllegalAccessException");
        }
    }

    static void inspectAfterOverride(NestAccessDemo.Vault vault)
            throws Exception {
        // Tạo Field mới để không làm sai phép kiểm chứng ban đầu.
        Field field = NestAccessDemo.Vault.class
                .getDeclaredField("secret");

        // Hai top-level classes của ví dụ đều ở cùng unnamed module.
        boolean opened = field.trySetAccessible();
        System.out.println("other.override.enabled=" + opened);
        if (opened) {
            System.out.println("other.override.canAccess="
                    + field.canAccess(vault));
            System.out.println("other.override.value=" + field.get(vault));
        }
    }
}
```

Chạy trong môi trường classpath thông thường:

```bash
javac NestAccessDemo.java
java NestAccessDemo
```

Kết quả dự kiến:

```text
nest.host=NestAccessDemo
same.nest=true
other.nest=false
nest.field.canAccess=true
nest.method.canAccess=true
nest.field.value=sample-value
nest.method.value=revealed:sample-value
other.field.canAccess=false
other.method.canAccess=false
other.field=IllegalAccessException
other.method=IllegalAccessException
other.override.enabled=true
other.override.canAccess=true
other.override.value=sample-value
```

### Điều gì đã được chứng minh?

- **Đích giống nhau:** `Vault` được tạo một lần, truyền cho cả `NestReader` và `IndependentReader`.
- **Member giống nhau:** Cả hai đều tìm trường `secret` và method `reveal`, không có sai khác về tên hoặc chữ ký.
- **Khác caller:** `NestReader` là nestmate của `Vault`; `IndependentReader` không phải nestmate. Kết quả `canAccess` vì vậy có thể khác nhau.
- **Có thử hành vi thật:** `field.get` và `method.invoke` từ `NestReader` thành công, trong khi hai lời gọi từ `IndependentReader` ném `IllegalAccessException`.
- **Override tách riêng:** `trySetAccessible` chỉ được thử sau khi kiểm tra quyền mặc định, dùng một `Field` mới. Việc bật override **không thay đổi** kết quả `isNestmateOf`.

Kết quả `other.override.enabled=true` ở trên giả định đúng điều kiện chạy đã mô tả: các class được biên dịch vào cùng unnamed module trong classpath. Không được mang kết quả đó áp đặt cho các class thuộc hai named modules khác nhau.

Chuỗi `sample-value` chỉ là dữ liệu giả. Trong dự án thực, không ghi secret hoặc token thật ra log để chứng minh quyền reflection.

## 5. Vì sao mỗi caller cần một phép thử riêng?

Reflection sử dụng thông tin về **class thực hiện thao tác**. Khi chạy ví dụ từ `main`:

```text
main()
  |
  +--> NestReader.inspect(vault)
  |       |
  |       +--> Field.canAccess(vault) / Field.get(vault)
  |             Caller trực tiếp: NestReader (cùng nest)
  |
  +--> IndependentReader.inspect(vault)
          |
          +--> Field.canAccess(vault) / Field.get(vault)
                Caller trực tiếp: IndependentReader (khác nest)
```

Nếu đổi chương trình để cả hai lớp gọi vào một `ReflectionUtility.readField(...)`, thì phép kiểm tra quyền thực tế diễn ra trong **`ReflectionUtility`**. Lúc đó phép đo không còn phản ánh quyền của từng lớp yêu cầu ban đầu. Vì vậy, muốn kiểm chứng ranh giới nest, hãy đặt lệnh `field.get` hoặc `method.invoke` **ngay trong các lớp caller cần so sánh**.

Mặt khác, nếu chuyển cùng một đối tượng `Field` đã bật override thành công cho caller khác, trạng thái override thuộc **đối tượng reflection** đó có thể khiến kết quả truy cập thay đổi. Để kiểm chứng quyền **mặc định**, mỗi caller nên lấy một `Field` hoặc `Method` mới và không gọi `setAccessible`/`trySetAccessible` trước khi đo.

## 6. Nestmates khác với quyền mở truy cập theo module

Cơ chế `trySetAccessible()` cho phép yêu cầu **bỏ qua kiểm tra quyền Java thông thường** khi điều kiện API/JPMS cho phép. Nó không biến hai class thành nestmates.

Trên JDK hiện đại:

- Trong cùng module, việc yêu cầu mở truy cập sâu tới member thông qua reflection thường được phép theo quy tắc của `AccessibleObject`. Ví dụ classpath ở trên thuộc cùng unnamed module nên `trySetAccessible()` trả về `true`.
- Khi caller thuộc **module khác**, việc một package được `exports` không có nghĩa private member trong package được mở cho reflection.
- Package được `opens` thích hợp có thể cho phép module khác thực hiện deep reflection. `setAccessible(true)` có thể ném `InaccessibleObjectException` nếu yêu cầu không được phép; `trySetAccessible()` cho biết thất bại bằng `false` trong các tình huống đó.
- Việc truy cập thành công sau khi bật override chỉ xác nhận cơ chế mở truy cập đối với đối tượng reflection và ngữ cảnh hiện tại, **không xác nhận** caller có quan hệ nest với class đích.

Ví dụ cấu hình module:

```java
module business.model {
    exports com.example.model;
    // Cho phép module inspection.tool truy cập sâu nếu có nhu cầu hợp lệ:
    opens com.example.model to inspection.tool;
}
```

`exports` dành cho khả năng dùng các API public theo điều kiện module; `opens` cho phép reflective access sâu tới package trong phạm vi được khai báo. Khi phát triển framework, nên làm rõ yêu cầu module ngay trong hợp đồng cấu hình thay vì giả định mọi member private đều luôn có thể được mở.

**Cảnh báo về mô hình quyền:** Khả năng truy cập private thông qua nest không phải một công tắc bạn có thể bật bằng reflection. `Class.isNestmateOf` cho thấy quan hệ do JVM xác định; `trySetAccessible` tác động đến việc kiểm tra truy cập của một đối tượng `AccessibleObject` cụ thể.

## 7. Phân loại đúng lỗi kiểm chứng

Một kiểm thử quyền reflection nên nhận diện lớp phát sinh lỗi:

| Quan sát | Lỗi/đặc điểm | Diễn giải |
| --- | --- | --- |
| Không tìm thấy trường đã khai báo | `NoSuchFieldException` tại `getDeclaredField` | Tên hoặc lớp khai báo không khớp |
| Không tìm thấy phương thức đúng chữ ký | `NoSuchMethodException` tại `getDeclaredMethod` | Tên hoặc danh sách kiểu tham số không khớp |
| Có metadata nhưng caller thiếu quyền | `IllegalAccessException` tại `Field.get`/`Method.invoke` | Kiểm tra truy cập không cho phép thao tác |
| Receiver null hoặc sai kiểu với instance member | Có thể là `NullPointerException`/`IllegalArgumentException` tùy thao tác | Sai đối số hoặc trạng thái của phép gọi, không phải quan hệ nest |
| Method được gọi rồi tự ném ngoại lệ | `InvocationTargetException` tại `Method.invoke` | Xem `getCause()` để biết lỗi từ thân method |
| Yêu cầu mở truy cập sâu qua `setAccessible(true)` bị JPMS từ chối | `InaccessibleObjectException` | Package/module chưa cho phép mở truy cập như yêu cầu |
| Yêu cầu `trySetAccessible()` bị từ chối | Trả về `false` | Caller không thể bật override trong ngữ cảnh đang xét |

**Không nhầm `InvocationTargetException` với `IllegalAccessException`.** Nếu reflective method được gọi thành công về mặt quyền nhưng thân method ném `IllegalStateException`, `invoke` sẽ bọc nguyên nhân đó trong `InvocationTargetException`. Ngược lại, khi không có quyền gọi method, `IllegalAccessException` phát sinh ở tầng reflection trước khi thân method chạy.

Một caller là nestmate vẫn có thể truyền receiver sai, tìm member không tồn tại, hoặc gọi method có lỗi nội bộ. Quan hệ nest chỉ giải quyết phần **quyền**, không bỏ qua các điều kiện hợp lệ khác.

### Trường `final` cũng cần hợp đồng riêng

Trong ví dụ `Vault`, trường `secret` được khai báo `private final`. Đọc qua `Field.get` khi caller đủ quyền là một trường hợp; việc ghi lại bằng `Field.set` là trường hợp khác với các giới hạn riêng, đặc biệt đối với final fields. Không suy diễn “đọc private được” thành “được phép thay đổi mọi private final field”. Thực hành đúng là đặt dữ liệu bất biến bằng constructor/factory có hợp đồng rõ ràng.

## 8. Cách lập kế hoạch kiểm thử theo caller

Với cùng một instance field private của một class public trong môi trường được mô tả:

| Caller | Quan hệ với target | `canAccess` trước override | `Field.get` trước override |
| --- | --- | --- | --- |
| Lớp khai báo member | Cùng class | `true` | Thành công |
| Một nested class thuộc cùng nest | Nestmate | `true` | Thành công |
| Top-level class khác, cùng package | Khác nest | `false` | `IllegalAccessException` |
| Top-level class khác, cùng module | Khác nest | `false` | `IllegalAccessException` |
| Caller ở named module khác, package chỉ được export | Khác nest | `false` đối với private | `IllegalAccessException` |

Bảng giả định receiver hợp lệ và `Field` mới, chưa bật override. Đây là các case cụ thể của **private instance field**. Không áp dụng máy móc bảng này cho public/protected/static members hoặc trường hợp có quyền truy cập khác.

Khi viết báo cáo kiểm thử, nên ghi: phiên bản JDK, lớp khai báo member, lớp caller thực sự gọi reflection, quan hệ `isNestmateOf`, receiver, loại member, kết quả `canAccess`, trạng thái override, kết quả `get`/`invoke` và nguyên nhân ngoại lệ nếu có. Không ghi giá trị private thật vào log. Có thể lấy phiên bản JDK thực tế bằng `Runtime.version()`.

## 9. Bài tập có lời giải

**Bài 1 — Cùng package có đủ không?** `User` có `private String passwordHash`, `Audit` là top-level class khác cùng package. `Audit` tìm được `Field` qua `getDeclaredField`. Nó có quyền `field.get(user)` mặc định không?

Không. Metadata có thể tìm thấy nhưng private member không tự mở cho một top-level class khác chỉ vì cùng package. Khi không cùng nest và chưa bật override, phép đọc thất bại vì quyền truy cập.

**Bài 2 — Caller nằm ở đâu?** `Outer.Reader` đọc được private field của `Outer.Target` và trả chuỗi cho `ExternalTool`. `ExternalTool` có cùng quyền gọi `Field.get` trực tiếp không?

Không. `Field.get` trong thử nghiệm đầu thực hiện ở `Outer.Reader`, là nestmate. Chuyển chính lệnh đó sang `ExternalTool` thay đổi caller được xét quyền.

**Bài 3 — Có đổi nest bằng `trySetAccessible` không?** `IndependentReader` bật override thành công và đọc được field. Sau đó `Vault.class.isNestmateOf(IndependentReader.class)` có đổi thành `true` không?

Không. Override không làm thay đổi quan hệ nest do JVM xác định.

**Bài 4 — Export và opens.** Một named module `exports com.example.model` nhưng không `opens` package đó cho module kiểm tra. Module kiểm tra có quyền dùng `trySetAccessible()` để đọc private field của class public không?

Không mặc nhiên. `exports` không phải giấy phép cho deep reflection vào private member. Cần xét quan hệ module và điều kiện mở package.

**Bài 5 — Ngoại lệ nào?** Caller là nestmate và `Method.invoke` ném `InvocationTargetException` với cause `IllegalStateException`. Có phải quyền private thất bại không?

Không. Method đã được gọi và thân method ném lỗi. Đọc `getCause()` để biết nguyên nhân; việc thiếu quyền ở tầng reflective invocation thường dẫn tới `IllegalAccessException`.

## 10. Ghi nhớ

1. Nestmates có thể truy cập private member của nhau theo quy tắc Java hiện đại; cùng package hoặc cùng tệp `.java` không đồng nghĩa cùng nest.
2. `getDeclaredField` và `getDeclaredMethod` tìm metadata; chúng không xác nhận quyền đọc hoặc gọi member.
3. `canAccess` và `Field.get`/`Method.invoke` xét ngữ cảnh **caller đang thực hiện thao tác**; hai callers khác nhau có thể nhận kết quả khác nhau.
4. `getNestHost`, `getNestMembers` và `isNestmateOf` giúp kiểm chứng quan hệ nest do JVM xác định.
5. `trySetAccessible` yêu cầu bỏ qua kiểm tra truy cập cho một đối tượng reflection; nó không tạo quan hệ nest và vẫn chịu giới hạn của JPMS.
6. Phải phân biệt lỗi metadata, lỗi quyền truy cập, receiver không hợp lệ và ngoại lệ do chính method được gọi ném.
7. Để kết luận chắc chắn, kiểm thử riêng từng caller trên đúng JDK/module đang sử dụng, giữ chứng cứ về member, receiver và trạng thái override.

Hiểu ranh giới quyền private trong nest giúp thiết kế kiểm chứng reflection chính xác, giữ nguyên tính đóng gói của Java và tránh phụ thuộc vào hành vi đã lỗi thời trên JDK hiện đại.
