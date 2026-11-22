# Fixture kiểm thử Reflection với `public`, `protected`, package-private và `private` member

Khi viết công cụ Java dựa trên Reflection (mapper, serializer, dependency injection, bộ tạo tài liệu API hoặc scanner), **chỉ nhìn thấy một member trong metadata không có nghĩa được phép đọc, gọi hoặc tạo instance qua member đó**. Một fixture tốt cần chủ động tạo đủ bốn mức truy cập của Java, đặt mã kiểm thử **ở cả cùng package lẫn khác package**, rồi kiểm tra hành vi thật thay vì suy đoán từ tên modifier.

Bài này thiết kế một fixture Java 17+ có **field, method và constructor** ở bốn mức `public`, `protected`, **package-private** (không ghi access modifier) và `private`. Ta quan sát sự khác nhau giữa `getFields()/getMethods()` với `getDeclaredFields()/getDeclaredMethods()`, và kiểm thử quyền bằng `AccessibleObject.canAccess(...)`, `trySetAccessible()` cùng quy tắc dành cho subclass/JPMS.

## 1. Bốn mức truy cập cần được thử trong fixture

| Modifier của member | Chính class/nestmate được phép | Class khác cùng package | Subclass ở package khác | Class không liên quan ở package khác |
| --- | --- | --- | --- | --- |
| `public` | Có | Có | Có | Có, nếu lớp/package đích cũng khả kiến |
| `protected` | Có | Có | Có, **với quy tắc receiver khi ở package khác** | Không |
| *package-private* (không modifier) | Có | Có | Không chỉ vì là subclass | Không |
| `private` | Có, theo quy tắc nestmate của Java | Không chỉ vì cùng package | Không chỉ vì kế thừa | Không |

Bảng trên mô tả quyền của **mã Java thông thường**, trước khi dùng một cơ chế reflective access suppression được cấp phép. Cần kiểm tra thêm khả năng truy cập của **lớp chứa member** và quan hệ module (`exports`/`opens`). `public` trên một member nằm trong lớp không public hoặc package không export không tự tạo thành API public toàn hệ thống.

- **Protected ở package khác:** subclass được quyền truy cập instance member `protected` qua một receiver có kiểu là chính subclass đó (hoặc subclass con thích hợp). Từ subclass ấy, thao tác cùng member trên một instance `BaseFixture` thông thường vẫn có thể bị từ chối.
- **Package-private:** phụ thuộc **runtime package**. Khi Java có các class loader/module khác nhau, chỉ cùng dòng tên package trong source không đủ để khẳng định cùng runtime package.
- **Private và nestmates:** những nested class cùng nest có cơ chế truy cập private riêng. Để thử thất bại private một cách rõ ràng, ví dụ sử dụng **ba lớp top-level ở các tệp riêng**, không đặt toàn bộ fixture vào nested class của test.
- **Constructor:** cũng có bốn mức quyền, nhưng không được kế thừa. Test constructor cần `getDeclaredConstructor(...)` hoặc `getConstructor(...)`, không áp dụng quy tắc override.

## 2. Xác định câu hỏi kiểm thử trước khi chọn API

Reflection có hai hoạt động khác nhau: **tìm metadata** và **sử dụng member**.

| API | Nó cho biết gì? | Không nên suy diễn |
| --- | --- | --- |
| `Class.getDeclaredField(name)` | Tìm field khai báo trực tiếp, gồm public/non-public | Không chứng minh caller có thể đọc/ghi field |
| `Class.getFields()` | Liệt kê các public field phù hợp, gồm field kế thừa | Không phải danh sách đầy đủ mọi field private của hierarchy |
| `Class.getDeclaredMethod(name, parameterTypes...)` | Tìm đúng method do lớp khai báo, không giới hạn modifier | Không chứng minh có quyền `invoke` |
| `Class.getMethods()` | Public methods phù hợp, có tính đến kế thừa/interface | Không trả toàn bộ non-public methods |
| `Class.getDeclaredConstructors()` | Constructor do lớp khai báo, mọi mức modifier | Không có constructor kế thừa |
| `Class.getConstructor(parameterTypes...)` | Tìm public constructor theo chữ ký | Constructor private/protected/package-private không xuất hiện |
| `Field.get`/`set`, `Method.invoke`, `Constructor.newInstance` | Thực hiện thao tác, có kiểm tra truy cập và điều kiện gọi | Không chỉ dựa vào việc đã tìm được metadata |
| `AccessibleObject.canAccess(receiver)` | Hỏi tại vị trí caller hiện tại có thể sử dụng member không, xét trạng thái accessible | Không tự thay đổi quyền; với field/method instance cần receiver phù hợp; với static member/constructor cần `null` |
| `AccessibleObject.trySetAccessible()` | Thử bật cờ bỏ qua kiểm tra truy cập Java ở những nơi được phép | Có thể trả `false` nếu bị module encapsulation ngăn; không cấp quyền vô điều kiện |

**Điểm thực hành:** `getDeclaredFields()` và các API trả mảng Reflection **không bảo đảm thứ tự**. Khi in kết quả để test/đối chiếu snapshot, hãy `sorted()`; nếu không, test sẽ phụ thuộc thứ tự ngẫu nhiên của môi trường thay vì ý nghĩa của access modifier.

`canAccess` không phù hợp làm một hàm tổng quát nhận `null` cho mọi member: với instance field và instance method, phải truyền receiver tương thích; constructor và static member dùng `null`. Nếu receiver sai loại, API có thể ném `IllegalArgumentException`. Nó cũng kiểm tra theo **caller thực tế**, nên cùng một `Field` có thể cho kết quả khác khi `canAccess` được gọi từ lớp test khác.

## 3. Fixture Java 17+: ba tệp, hai package và nhiều ngữ cảnh caller

Cấu trúc thư mục:

~~~text
fixture/
  BaseFixture.java
  SamePackageProbe.java
client/
  FixtureAccessDemo.java
~~~

Ba class này được biên dịch và chạy trên **classpath/unnamed module** để cô lập quy tắc modifier/package trước khi thử named modules. Cùng tên package trong hai source file đi kèm cùng class loader, nên được xem là cùng runtime package.

### 3.1. `fixture/BaseFixture.java`

Định nghĩa đủ bốn mức truy cập cho **field, constructor và method**:

~~~java
package fixture;

public class BaseFixture {
    public int publicField = 10;
    protected int protectedField = 20;
    int packageField = 30;
    private int privateField = 40;

    public BaseFixture() {}
    protected BaseFixture(String text) {}
    BaseFixture(int number) {}
    private BaseFixture(boolean value) {}

    public String publicMethod() { return "public"; }
    protected String protectedMethod() { return "protected"; }
    String packageMethod() { return "package"; }
    private String privateMethod() { return "private"; }
}
~~~

- Không có từ khóa modifier trước `packageField`/`packageMethod`/`BaseFixture(int)` nghĩa là **package-private**, không phải `protected`.
- `privateField` vẫn tồn tại trong metadata của `BaseFixture`; việc test bên ngoài không được truy cập trực tiếp không có nghĩa field này bị Reflection “ẩn hoàn toàn”.
- Các constructor được cố ý cho kiểu tham số khác nhau. Vì Java không cho hai constructor trùng parameter signature chỉ khác modifier, đó là cách tạo fixture với cả bốn mức quyền mà vẫn hợp lệ.

### 3.2. `fixture/SamePackageProbe.java`

Một caller **khác class, cùng package** kiểm tra các field và constructor:

~~~java
package fixture;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class SamePackageProbe {
    public static void run() throws Exception {
        BaseFixture base = new BaseFixture();
        for (String name : new String[]{
                "publicField", "protectedField", "packageField", "privateField"}) {
            Field f = BaseFixture.class.getDeclaredField(name);
            System.out.println("same-package " + name + ": " + f.canAccess(base));
        }
        Constructor<?> ctor = BaseFixture.class.getDeclaredConstructor(int.class);
        System.out.println("same-package constructor: " + ctor.canAccess(null));
    }
}
~~~

Quan sát kỳ vọng: `public`, `protected` và package-private đều `true`, còn `private` trả `false`. `SamePackageProbe` không phải nestmate của `BaseFixture`; cùng package không đủ để truy cập private.

`getDeclaredConstructor(int.class)` tìm constructor package-private. `ctor.canAccess(null)` trả `true` do caller `SamePackageProbe` thuộc cùng runtime package. Đây là kiểm tra quyền constructor, với receiver bắt buộc là `null`.

### 3.3. `client/FixtureAccessDemo.java`

Một caller ở **package khác** đồng thời là subclass, giúp thấy ràng buộc receiver của `protected`:

~~~java
package client;

import fixture.BaseFixture;
import fixture.SamePackageProbe;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.stream.Collectors;

public class FixtureAccessDemo extends BaseFixture {
    private void checkProtected() throws Exception {
        Field f = BaseFixture.class.getDeclaredField("protectedField");
        System.out.println("subclass receiver protected: " + f.canAccess(this));
        System.out.println("base receiver protected: " +
                f.canAccess(new BaseFixture()));
    }

    public static void main(String[] args) throws Exception {
        BaseFixture base = new BaseFixture();

        System.out.println("declared fields: " +
                Arrays.stream(BaseFixture.class.getDeclaredFields())
                        .map(Field::getName).sorted()
                        .collect(Collectors.joining(", ")));
        System.out.println("public fields: " +
                Arrays.stream(BaseFixture.class.getFields())
                        .filter(f -> f.getDeclaringClass() == BaseFixture.class)
                        .map(Field::getName).sorted()
                        .collect(Collectors.joining(", ")));

        for (String name : new String[]{
                "publicField", "protectedField", "packageField", "privateField"}) {
            Field f = BaseFixture.class.getDeclaredField(name);
            System.out.println("client " + name + ": " + f.canAccess(base));
        }

        System.out.println("public method: " +
                BaseFixture.class.getMethod("publicMethod").invoke(base));
        try {
            BaseFixture.class.getMethod("privateMethod");
            System.out.println("unexpected lookup");
        } catch (NoSuchMethodException expected) {
            System.out.println("getMethod(private): NoSuchMethodException");
        }

        SamePackageProbe.run();
        new FixtureAccessDemo().checkProtected();

        Field privateField = BaseFixture.class.getDeclaredField("privateField");
        System.out.println("private trySetAccessible: " +
                privateField.trySetAccessible());
        System.out.println("private field value: " + privateField.getInt(base));
    }
}
~~~

Lưu ý `FixtureAccessDemo` là subclass của `BaseFixture` nhưng vòng lặp `canAccess(base)` truyền một **receiver thuộc chính `BaseFixture`**, không thuộc `FixtureAccessDemo`. Điều này được cố ý để thử tình huống `protected` bị từ chối xuyên package. Trong `checkProtected()`, receiver `this` lại là instance của subclass, nên phép kiểm tra `protected` thành công.

### 3.4. Biên dịch, chạy và kiểm tra stdout

Từ thư mục chứa hai folder `fixture` và `client`, tạo thư mục `out` rồi chạy:

~~~bash
mkdir out
javac --release 17 -d out fixture/BaseFixture.java fixture/SamePackageProbe.java client/FixtureAccessDemo.java
java -cp out client.FixtureAccessDemo
~~~

Kết quả đã đối chiếu bằng JDK với `--release 17`:

~~~text
declared fields: packageField, privateField, protectedField, publicField
public fields: publicField
client publicField: true
client protectedField: false
client packageField: false
client privateField: false
public method: public
getMethod(private): NoSuchMethodException
same-package publicField: true
same-package protectedField: true
same-package packageField: true
same-package privateField: false
same-package constructor: true
subclass receiver protected: true
base receiver protected: false
private trySetAccessible: true
private field value: 40
~~~

**Giải thích các kết quả quan trọng:**

1. `declared fields` liệt kê cả bốn field, vì `getDeclaredFields()` không lọc theo `public`. `public fields` chỉ có `publicField` trong fixture (đã lọc theo `getDeclaringClass()`).
2. Ở vòng lặp `client`, `canAccess(base)` chỉ đúng cho `publicField`. Ba field còn lại không tự trở nên truy cập được vì đã lấy `Field` từ `getDeclaredField`.
3. `BaseFixture.class.getMethod("privateMethod")` không tìm thấy vì API này chỉ tìm public method: nó ném **`NoSuchMethodException`**. Nếu dùng `getDeclaredMethod("privateMethod")` sẽ tìm được metadata, nhưng việc `invoke` còn cần quyền.
4. `SamePackageProbe` thấy được `protectedField` và `packageField`. `privateField` vẫn bị từ chối vì hai lớp top-level không phải nestmates.
5. `subclass receiver protected: true` nhưng `base receiver protected: false` chứng minh điều kiện receiver đặc thù của `protected` khi caller là subclass khác package.
6. `private trySetAccessible: true` là kết quả trong ví dụ chạy **trên classpath/unnamed module**. `trySetAccessible()` có thể trả `false` trong một ứng dụng named modules nếu package đích không `opens` tới module caller. Không dùng kết quả `true` ở đây để tuyên bố Java luôn cho vượt quyền private.
7. Sau khi `trySetAccessible()` thành công, `getInt(base)` có thể đọc giá trị `privateField = 40`. Đây là thao tác chủ động yêu cầu suppress access checks trong ngữ cảnh được phép, khác với kiểm tra truy cập mặc định bằng `canAccess`.

## 4. Mở rộng cùng fixture sang kiểm thử method và constructor

Đối với method, dùng cùng các tên từ `BaseFixture`:

| Method | Tìm bằng `getDeclaredMethod(...)` | Tìm bằng `getMethod(...)` | Quyền gọi mặc định từ class khác package |
| --- | --- | --- | --- |
| `publicMethod()` | Có | Có | Được, nếu lớp/package đích khả kiến |
| `protectedMethod()` | Có | Không theo API này trên fixture chỉ có member protected | Phụ thuộc subclass và receiver |
| `packageMethod()` | Có | Không | Không |
| `privateMethod()` | Có | Không | Không |

Nếu muốn test **quyền invocation** thay vì khả năng lookup, trước tiên lấy `Method m = BaseFixture.class.getDeclaredMethod("privateMethod")`, rồi gọi `m.canAccess(base)` hoặc `m.invoke(base)`; trường hợp không được phép invoke sẽ báo `IllegalAccessException`. `NoSuchMethodException` lại thuộc bước **tìm method theo API/chữ ký**. Đừng gộp hai nguyên nhân này thành cùng một lỗi.

Với constructor:

- `BaseFixture.class.getConstructor()` tìm được constructor public không tham số.
- `BaseFixture.class.getDeclaredConstructor(String.class)` tìm thấy constructor `protected`.
- `BaseFixture.class.getDeclaredConstructor(int.class)` tìm thấy constructor package-private.
- `BaseFixture.class.getDeclaredConstructor(boolean.class)` tìm thấy constructor `private`.
- `BaseFixture.class.getConstructor(boolean.class)` ném `NoSuchMethodException` vì constructor tương ứng không public.

`Constructor.canAccess(null)` kiểm tra quyền tại caller hiện tại; dùng `null` vì constructor chưa có đối tượng receiver. `newInstance(...)` có thể ném `IllegalAccessException` khi không được phép gọi constructor, `InvocationTargetException` nếu chính constructor ném exception, hoặc `InstantiationException` với class abstract; những ngoại lệ này không được nhầm với lỗi không tìm thấy constructor.

Khi kiểm thử từng loại member, nên tạo **bộ case độc lập** (field lookup, field get/set, method lookup/invoke, constructor lookup/newInstance) với expected exception cụ thể. Nếu chỉ viết một phép thử duy nhất `getDeclaredXxx`, fixture mới kiểm chứng khả năng nhìn metadata chứ chưa kiểm chứng quyền sử dụng.

## 5. Named modules, `exports` và `opens` thay đổi điều gì?

Ví dụ ở mục 3 cố ý chạy classpath trong unnamed module. Một bộ test cho **JPMS** cần dùng các named module riêng, bởi vì `exports` và `opens` kiểm soát những khía cạnh khác nhau:

- `exports fixture;` cho phép module khác (nếu đọc module đích) dùng các **public types/public members** của package `fixture` theo luật truy cập bình thường. Nó không cho bên ngoài tùy ý gọi `privateMethod`.
- `opens fixture to client.app;` cấp khả năng **deep reflection** tới package `fixture` cho module `client.app`, khi các điều kiện API và module khác được đáp ứng. `opens` không tự biến member private thành public Java source.
- Nếu package không open cho bên gọi, `trySetAccessible()` trên private member ở module khác có thể trả `false`, còn `setAccessible(true)` có thể ném `InaccessibleObjectException`.
- Các module có thể sử dụng `--add-opens source.module/fixture=client.app` cho nhu cầu chẩn đoán có kiểm soát, nhưng không nên coi cờ này là điều kiện mặc định để ứng dụng hoạt động.

Ví dụ minh họa riêng về descriptor (không phải các file bắt buộc để chạy demo classpath phía trên):

~~~java
// module-info.java của module fixture.lib:
module fixture.lib {
    exports fixture;
    opens fixture to client.app;
}

// module-info.java của module client.app:
module client.app {
    requires fixture.lib;
}
~~~

Nếu muốn kiểm thử chặn deep reflection, hãy tạo thêm fixture ở một **named module không opens package** và xác nhận `trySetAccessible()` thất bại từ module khác. Cần lưu ý cách khởi chạy/module path, không dùng kết quả của classpath demo làm expected output cho test JPMS.

## 6. Thiết kế ma trận kiểm thử ổn định

Không nên thiết kế fixture chỉ để “chạy được một lần”. Với công cụ Reflection, nên có ma trận kiểm chứng rõ:

| Trục thử | Những trường hợp tối thiểu |
| --- | --- |
| Thành viên | Field, method, constructor; cân nhắc static, inherited, final ở test mở rộng |
| Modifier | `public`, `protected`, package-private, `private` |
| Quan hệ caller | Chính class, class cùng package khác nest, subclass khác package, class không liên quan khác package |
| Receiver | Đúng subclass receiver, base-class receiver, `null` cho static/constructor, receiver không tương thích |
| Lookup | `getDeclaredXxx` đối chiếu `getXxx`; kiểm tra `NoSuchFieldException`/`NoSuchMethodException` |
| Sử dụng | `canAccess`, `Field.get/set`, `Method.invoke`, `Constructor.newInstance`, `trySetAccessible` |
| Module | Classpath unnamed module, named modules `exports`, named modules `opens`/không `opens` |
| Kết quả | Đúng dữ liệu, đúng exception, metadata đầy đủ, định dạng log và thứ tự ổn định |

**Không dùng thứ tự mảng Reflection làm expected output.** Thực hiện `sorted()` hoặc so tập hợp nếu thứ tự không có ý nghĩa. Tránh test phụ thuộc vào `setAccessible(true)` trên các package JDK bị đóng; mục tiêu ở đây là kiểm chứng các luật truy cập của fixture, không phải tìm cách vô hiệu hóa encapsulation.

Nếu thử với nested class, hãy ghi rõ chúng thuộc nest nào bằng `Class.getNestHost()` và `getNestMembers()`. Một nested test class có thể có quyền private đối với enclosing class ngay từ đầu, khiến phép thử “private phải bị từ chối” trở thành **false negative về thiết kế test**.

## 7. Lỗi thường gặp khi dùng fixture

1. **Chỉ có class public:** không chứng minh công cụ xử lý protected/package-private/private đúng.
2. **Đặt fixture và runner trong cùng class/nest:** các quyền private có thể được chia sẻ, làm mất case cần bị từ chối.
3. **Lấy `Field` thành công rồi kết luận có quyền đọc:** metadata lookup và access check là hai bước độc lập.
4. **Dùng `getMethods()` để tìm private method:** API đó chỉ phục vụ public methods; muốn metadata private dùng `getDeclaredMethod`.
5. **Dùng `canAccess(null)` cho instance field:** truyền sai receiver; phải cấp instance đúng kiểu.
6. **Dùng `trySetAccessible()` rồi bỏ qua trạng thái:** nó trả boolean; khi không cho phép cần xử lý `false` đúng.
7. **Nhầm protected member với public cho mọi subclass receiver:** ở package khác, receiver của instance member chịu quy tắc riêng.
8. **Dựa vào named module mà vẫn dùng expected output của classpath:** JPMS có thể thay đổi kết quả reflective access.
9. **So sánh danh sách method/field theo thứ tự Reflection trả về:** không có cam kết thứ tự, gây test không ổn định.
10. **Không phân biệt exception lookup với exception invoke:** thiếu method và thiếu quyền gọi là hai nguyên nhân khác nhau.

**Ghi nhớ:** một fixture Reflection hữu ích phải tách bạch **metadata thấy được**, **truy cập mặc định theo caller/receiver**, và **quyền deep reflection được cấp có điều kiện**. Ví dụ ba lớp ở hai package vừa cho thấy đủ bốn access modifier, vừa chứng minh tại sao `protected`, package-private và `private` cần được test từ nhiều ngữ cảnh, không chỉ một lớp đơn lẻ.

**Tài liệu đối chiếu:**
- [`Class` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [`AccessibleObject` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [`Field` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html)
- [`Constructor` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html)