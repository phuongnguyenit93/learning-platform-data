# Tên và cấu trúc do compiler sinh không phải hợp đồng ứng dụng

Trong Java Reflection, chương trình có thể nhìn thấy kiểu lồng, tên lớp, constructor, field và method của bytecode đã nạp. Nhưng **không phải mọi thứ nhìn thấy qua Reflection đều là hợp đồng ứng dụng**. Compiler có thể thêm phương thức cầu nối, accessor, field giữ biến capture hoặc lớp phục vụ biểu thức anonymous. Tên/số lượng/cách bố trí nhiều thành phần này phụ thuộc compiler, target bytecode và cách sửa source.

Bài này thuộc chủ đề **Kiểu lồng và nest** của Java Reflection. Ta sẽ phân biệt metadata được đặc tả với chi tiết phát sinh trong quá trình biên dịch, rồi sử dụng `Class<?>` đúng cách để tránh gắn logic nghiệp vụ với tên như `Outer$1`, `access$000` hoặc `this$0`.

## 1. Ba tầng cần phân biệt

1. **Ngữ nghĩa source:** member class, local class, anonymous class, lambda, quy tắc truy cập private và tên kiểu Java. Java Language Specification (JLS) định nghĩa ý nghĩa các cấu trúc này.
2. **Biểu diễn runtime/class file:** binary name, constructor parameter, field, method, cờ `synthetic`/`bridge` và thuộc tính class file như `InnerClasses`, `EnclosingMethod`, `NestHost`/`NestMembers`. Một số chi tiết được đặc tả; một số do compiler lựa chọn.
3. **Hợp đồng ứng dụng:** kiểu/interface công bố, API ổn định, annotation/schema/registry do ứng dụng thiết kế. Đây mới là lớp mà logic nghiệp vụ, dữ liệu lưu lâu dài và các module khác nên phụ thuộc.

Điểm tinh tế: **binary name của member class có tên được JLS quy định** (ví dụ `pkg.Outer$Inner`), còn **số trong tên của local/anonymous class không phải ID nghiệp vụ ổn định**. Không nên gọi tất cả tên chứa `$` là “ngẫu nhiên”, và cũng không được suy ngược rằng tất cả tên đó có ý nghĩa ứng dụng.

## 2. Nhận diện đúng các loại class

| Loại | Khai báo/nguồn tạo | Reflection thích hợp | Không nên giả định |
| --- | --- | --- | --- |
| Member class hoặc interface | Khai báo trực tiếp bên trong một class/interface | `isMemberClass()`, `getDeclaringClass()` | Mọi class có dấu `$` đều là member |
| Local class | Khai báo trong block, thường ở phương thức | `isLocalClass()`, `getEnclosingMethod()` | Số xuất hiện trong binary name là thứ tự/ID ổn định |
| Anonymous class | Biểu thức tạo lớp vô danh | `isAnonymousClass()`, `getEnclosingClass()` | Luôn được phép gọi qua tên `$1` |
| Lambda | Biểu thức chức năng như `() -> ...` | Functional interface và hành vi của nó | Luôn có file `.class` hoặc tên runtime tái sử dụng được |
| Synthetic/bridge member | Compiler sinh hỗ trợ bytecode | `Member.isSynthetic()`, `Method.isBridge()` | Tên/số lượng method/field phát sinh là API |

`isSynthetic()` không phải phép thử nhận diện mọi local hay anonymous class. `getDeclaredClasses()` chỉ liệt kê member class/interface được khai báo trực tiếp trong một class, **không quét** mọi local/anonymous class từng xuất hiện trong các phương thức của nó.

### Ví dụ Java 17+: metadata thay cho cắt chuỗi tên

Lưu thành `ReflectionKindsDemo.java`:

```java
public class ReflectionKindsDemo {
    static class Member { }

    static Class<?> localClass() {
        class Local { }
        return Local.class;
    }

    static Class<?> anonymousClass() {
        Runnable task = new Runnable() {
            @Override
            public void run() { }
        };
        return task.getClass();
    }

    static void show(String label, Class<?> type) {
        System.out.printf(
            "%s: member=%s, local=%s, anonymous=%s, canonical=%s%n",
            label,
            type.isMemberClass(),
            type.isLocalClass(),
            type.isAnonymousClass(),
            type.getCanonicalName()
        );
    }

    public static void main(String[] args) {
        show("member", Member.class);
        show("local", localClass());
        show("anonymous", anonymousClass());
    }
}
```

```bash
javac ReflectionKindsDemo.java
java ReflectionKindsDemo
```

Kết quả:

```text
member: member=true, local=false, anonymous=false, canonical=ReflectionKindsDemo.Member
local: member=false, local=true, anonymous=false, canonical=null
anonymous: member=false, local=false, anonymous=true, canonical=null
```

Member `Member` có canonical name; local và anonymous class thì `getCanonicalName()` trả `null`. Các phương thức `isMemberClass()`, `isLocalClass()` và `isAnonymousClass()` trả lời chính xác ý nghĩa cần phân loại. Nếu in thêm `type.getName()`, một bản `javac` thường có thể tạo tên kiểu `ReflectionKindsDemo$Member`, `ReflectionKindsDemo$1Local` và `ReflectionKindsDemo$1`. Các số ở đây chỉ là ví dụ quan sát, **không phải output được kiểm thử hay ID bền vững**.

## 3. Binary name, canonical name và simple name

- `Class.getName()` phản ánh tên runtime, với class thông thường là binary name. Với member class `pkg.Outer.Inner` có tên, binary name theo JLS là `pkg.Outer$Inner`.
- `getCanonicalName()` thích hợp cho kiểu có canonical name; local/anonymous class trả `null`.
- `getSimpleName()` cho simple name; anonymous class có simple name rỗng.
- `getTypeName()` cho tên dạng dễ đọc hơn trong một số ngữ cảnh nhưng cũng không phải định danh nghiệp vụ.
- `Class.forName(...)` nhận binary name thích hợp, chịu ảnh hưởng của class loader và khả năng nạp lớp.

Ví dụ minh họa (giả sử đã có member type `pkg.Outer.Inner`):

```java
Class<?> member = Class.forName("pkg.Outer$Inner");
```

Dùng binary name của **một member class có tên đã biết và được công bố** là hợp lệ. Trái lại, đoán `pkg.Outer$1` để gọi một anonymous class là phụ thuộc vào cách compiler đánh số. Cũng đừng suy luận “tách tại dấu `$` cuối cùng” để xác định class bao ngoài: `$` có thể là ký tự hợp lệ trong tên định danh Java; hơn nữa class local, anonymous và synthetic có những ý nghĩa khác member class.

Ví dụ dễ vỡ:

```java
String binaryName = type.getName();
String guessedRole = binaryName.substring(binaryName.lastIndexOf('$') + 1);

// Không dùng guessedRole làm quyền truy cập, tên plugin hoặc khóa database.
```

Một định danh được lưu vào database, file cấu hình, sự kiện hoặc JSON nên là **khóa được ứng dụng định nghĩa**, không phải một mảnh tên do compiler gán.

## 4. Quan hệ khai báo, ngữ cảnh bao và tập kiểu lồng

Các API này trả lời những câu hỏi khác nhau:

| API | Đúng nghĩa | Giới hạn |
| --- | --- | --- |
| `getDeclaringClass()` | Class/interface khai báo kiểu này như **member** | Local/anonymous không có declaring class như member |
| `getEnclosingClass()` | Class bao gần nhất | Có thể có cho member, local, anonymous |
| `getEnclosingMethod()` | Phương thức bao trực tiếp local/anonymous class | Có thể `null` nếu nằm trong constructor/initializer |
| `getEnclosingConstructor()` | Constructor bao trực tiếp local/anonymous class | Không phải constructor được dùng để tạo mọi instance |
| `getDeclaredClasses()` | Member class/interface khai báo trực tiếp | Không gồm member kế thừa, local hoặc anonymous |
| `getClasses()` | Member type public, kể cả được kế thừa | Không giống `getDeclaredClasses()` |

Với `ReflectionKindsDemo`, `Member.class.getDeclaringClass() == ReflectionKindsDemo.class`. Với local/anonymous class tạo trong static method, `getDeclaringClass()` trả `null` nhưng `getEnclosingClass()` có thể cho biết `ReflectionKindsDemo.class`.

Nếu viết công cụ tạo tài liệu, hãy nêu rõ mục tiêu là **các member type được khai báo**, **các class cùng nest**, hay **mọi class đã nạp trong runtime**. Không API nào ở bảng trên tương đương với truy vấn “toàn bộ kiểu trong một file source”. Tập kết quả Reflection cũng không nên được coi là có thứ tự khai báo đảm bảo; khi cần trình bày ổn định, hãy sắp xếp theo quy tắc riêng và xử lý trường hợp trùng khóa.

## 5. Nestmates của JVM: cùng nest không có nghĩa cùng một cấu trúc tên

Từ Java 11, JVM hỗ trợ **nest-based access control**. Metadata class file như `NestHost` và `NestMembers` mô tả những lớp cùng nest để JVM kiểm tra quyền truy cập private. Cần phân biệt:

- `getNestHost()`: host của nest hiện tại.
- `isNestmateOf(other)`: kiểm tra hai class có chung nest host.
- `getNestMembers()`: trả các class mà nest host ghi nhận là thành viên. Thứ tự không được bảo đảm; API này cũng không liệt kê hidden class được thêm vào nest động qua `Lookup.defineHiddenClass`.

Lưu ví dụ thành `NestAccessDemo.java`:

```java
public class NestAccessDemo {
    private static String secret() {
        return "ready";
    }

    static class Helper {
        static String call() {
            return secret();
        }
    }

    public static void main(String[] args) {
        System.out.println(Helper.class.getNestHost() == NestAccessDemo.class);
        System.out.println(NestAccessDemo.class.isNestmateOf(Helper.class));
        System.out.println(Helper.call());
    }
}
```

```bash
javac NestAccessDemo.java
java NestAccessDemo
```

```text
true
true
ready
```

Kết quả thể hiện quan hệ nest và quyền gọi method `private` thông qua code hợp lệ. **Không kết luận hai lớp là nestmate từ việc cùng tiền tố trước dấu `$`.** JVM kiểm tra theo metadata và quy tắc của nó; `getNestMembers()` cũng không thay thế `getDeclaredClasses()`. Một local/anonymous class có thể là nestmate mà không phải member class khai báo trực tiếp.

Với target bytecode cũ hơn Java 11, compiler Java từng cần tạo synthetic accessor (thường nhìn thấy tên dạng `access$...`) cho một số truy cập private xuyên qua lớp lồng. Khi dùng nest metadata, nhu cầu sinh accessor kiểu đó thay đổi. Vì vậy, **không có API công khai mang tên `access$000` để logic ứng dụng được quyền phụ thuộc**.

## 6. Các thành phần compiler có thể bổ sung

### 6.1. Bridge method do erasure hoặc covariant return

Generics bị xóa kiểu ở bytecode. Để duy trì dispatch/override đúng, compiler có thể tạo **bridge method**. `Method.isBridge()` chỉ ra cờ bridge, còn `Method.isSynthetic()` chỉ ra cờ synthetic.

Lưu thành `MethodMetadataDemo.java`:

```java
import java.lang.reflect.Method;

public class MethodMetadataDemo {
    static class Parent<T> {
        T value() { return null; }
    }

    static class Child extends Parent<String> {
        @Override
        String value() { return "ok"; }
    }

    public static void main(String[] args) {
        for (Method method : Child.class.getDeclaredMethods()) {
            System.out.printf(
                "%s: bridge=%s, synthetic=%s%n",
                method.getName(),
                method.isBridge(),
                method.isSynthetic()
            );
        }
    }
}
```

Biên dịch bằng `javac MethodMetadataDemo.java` và chạy `java MethodMetadataDemo`. Trên `javac` JDK 17, thông thường sẽ quan sát được hai method tên `value`: method trả `String` được khai báo ở source (`bridge=false, synthetic=false`) và bridge method trả `Object` (`bridge=true, synthetic=true`). **Thứ tự các dòng không được bảo đảm**, nên bài không cố định output theo thứ tự. Cờ metadata hữu ích cho công cụ quan sát; code nghiệp vụ không nên gọi method theo “vị trí thứ hai” trong mảng Reflection.

### 6.2. Field giữ outer instance và biến capture

Non-static inner class có mối liên hệ với enclosing instance. Constructor phản chiếu có thể có tham số instance bao ngoài; với non-static inner class được khai báo trong ngữ cảnh như vậy, Java Reflection mô tả tham số này ở đầu danh sách constructor parameter. Local/anonymous class có thể cần giữ biến được capture.

Một compiler có thể biểu diễn state trợ giúp bằng field với tên dạng `this$0` hoặc `val$...`. Nhưng **tên field, cách tối ưu và việc field có tồn tại hay không không phải schema**. Đừng dùng `getDeclaredFields()` rồi mặc định serialize toàn bộ field, hay xem `this$0` như property nghiệp vụ.

### 6.3. Constructor, parameter name và synthetic members

`getDeclaredConstructors()` phản chiếu constructor thực có trong class file; constructor của inner/local/anonymous class có thể có tham số không được viết tường minh trong source. Metadata tên tham số còn phụ thuộc cách biên dịch, ví dụ tùy chọn `javac -parameters`. Khi cần, kiểm tra `Parameter.isNamePresent()`, `isImplicit()` và `isSynthetic()` thay vì đoán tên `arg0` hay dùng độ dài signature làm dữ liệu bất biến.

`getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructors()` không hứa thứ tự source. Các công cụ ánh xạ schema hoặc tạo tài liệu cần chọn rõ member nào thuộc hợp đồng, sau đó tự sắp xếp. Nếu lọc hết `isSynthetic()`/`isBridge()`, phải xác định rằng mục tiêu của mình là API source-level; một công cụ phân tích bytecode hoặc dispatch có thể cần giữ thành phần bridge.

### 6.4. Lambda và lớp triển khai ẩn

Lambda nên được nhìn như một cách tạo thực thể thực thi **functional interface**, không phải nguồn sinh class có tên bền vững. JVM/compiler có nhiều chiến lược triển khai, gồm cơ chế hidden class trong các JDK hiện đại. Không cố `Class.forName` bằng tên lấy từ `someLambda.getClass().getName()` để phục hồi chức năng trong lần chạy khác. Hãy lưu cấu hình/loại nghiệp vụ riêng và tái tạo đối tượng qua API đã thiết kế.

## 7. Thiết kế hợp đồng Reflection chủ đích

Nếu ứng dụng cần xác định class nào đảm nhận vai trò `parser`, đừng nhận diện bằng hậu tố `$Parser` hoặc số thứ tự anonymous class. Dùng interface + annotation runtime để công bố ý nghĩa.

Lưu thành `StableDiscoveryDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public class StableDiscoveryDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Role {
        String value();
    }

    @Role("parser")
    public static class Parser implements Runnable {
        @Override
        public void run() { }
    }

    public static void main(String[] args) {
        Class<?> type = Parser.class;
        if (Runnable.class.isAssignableFrom(type)) {
            Role role = type.getAnnotation(Role.class);
            System.out.println(role == null ? "unknown" : role.value());
        }
    }
}
```

```bash
javac StableDiscoveryDemo.java
java StableDiscoveryDemo
```

```text
parser
```

`Runnable` thể hiện hợp đồng hành vi; `@Role("parser")` công bố vai trò có thể truy vấn bằng Reflection. Việc *tìm* tất cả class ứng viên trong classpath là vấn đề discovery/registry khác: `getDeclaredClasses()` không phải chức năng quét package/classpath.

Áp dụng vào hệ thống thực tế:

1. **Phân loại kiểu:** dùng `isMemberClass()`, `isLocalClass()`, `isAnonymousClass()`; dùng `getDeclaringClass()` và `getEnclosingClass()` theo ý nghĩa tương ứng.
2. **Kiểm tra cùng nest:** dùng `getNestHost()`/`isNestmateOf()`, không so tiền tố chuỗi tên.
3. **Lập tài liệu API:** công bố type/member được thiết kế làm API, phân biệt compiler member bằng metadata khi phù hợp, kiểm soát thứ tự hiển thị.
4. **Định danh qua nhiều phiên bản:** định nghĩa khóa ổn định trong schema/annotation/cấu hình; không dùng số compiler sinh, thứ tự mảng Reflection hoặc tên triển khai lambda.
5. **Khởi tạo qua Reflection:** dựa vào constructor và kiểu tham số thực được công bố, xử lý ngoại lệ; tránh truy cập field/private accessor nội bộ.
6. **Kiểm thử tương thích:** kiểm tra hành vi và public contract. Chỉ kiểm tra tên/số lượng synthetic member nếu đang viết công cụ phân tích dành riêng cho compiler/bytecode đó.

## 8. Các lỗi thiết kế thường gặp

| Lỗi | Vấn đề | Cách sửa |
| --- | --- | --- |
| Dùng `getName().contains("$")` làm điều kiện “là inner class” | `$` không đủ nhận diện loại class | Dùng `isMemberClass()` hoặc API phân loại khác |
| Lưu `Outer$1` để nhận diện callback | Số có thể đổi theo source/compiler | Lưu registry key hoặc metadata tường minh |
| Dùng `getDeclaredClasses()` để tìm local class | Method chỉ trả member type khai báo trực tiếp | Phân biệt source analysis với member reflection |
| Dùng `getNestMembers()` làm sơ đồ khai báo class | Quan hệ nest phục vụ JVM access, phạm vi khác | Dùng `getDeclaringClass()`/`getDeclaredClasses()` |
| Phụ thuộc vào `access$000` hoặc `this$0` | Compiler/target có thể thay đổi thành phần | Thiết kế API và schema ổn định |
| Serialize toàn bộ `getDeclaredFields()` | Ghi cả state nội bộ, outer ref hoặc field hỗ trợ | Chọn DTO/record/property được chỉ định |
| Giả định phương thức đầu trong `getDeclaredMethods()` là public API | Thứ tự không được bảo đảm, có thể có bridge | Lọc và sắp xếp theo hợp đồng |
| Cho rằng tên triển khai lambda load lại được ở tiến trình khác | Kiểu triển khai runtime không có danh tính bền vững | Dựa vào functional interface, factory hoặc cấu hình |
| Lọc synthetic members một cách tuyệt đối | Có thể bỏ qua bridge cần nghiên cứu | Lọc theo mục đích công cụ, không tùy tiện |

### Tình huống: mapper làm rò rỉ state nội bộ

Một mapper tự động lấy mọi field của non-static inner class bằng `getDeclaredFields()` rồi ghi thẳng thành JSON. Nếu bytecode chứa field giữ outer instance hoặc biến capture, mapper có thể vô tình đưa vào JSON state không thuộc domain, gây vòng tham chiếu hoặc tạo output không nhất quán giữa các bản build.

Giải pháp đúng là **định nghĩa schema dữ liệu**: DTO, record hoặc danh sách thuộc tính được chỉ định rõ bằng annotation/cấu hình. `isSynthetic()` chỉ là thông tin hỗ trợ, không thay thế hợp đồng serialize.

## 9. Quan sát bytecode đúng cách

Sau khi đã tạo `NestAccessDemo.java`, có thể tự khảo sát:

```bash
javac --release 17 NestAccessDemo.java
javap -p NestAccessDemo
javap -v NestAccessDemo
```

`javap -p` hiển thị các thành viên kể cả private; `javap -v` cung cấp thêm attributes như metadata nest khi class file có chúng. Thử đổi compiler hoặc target để quan sát sự khác biệt, nhưng đừng biến một bản output cụ thể của `javap` thành luật bất biến.

Khi đọc kết quả, hãy luôn tự hỏi đó là:

- **Quy tắc được đặc tả** (chẳng hạn binary name của member type, semantics của nest access);
- **Hiện tượng ở một bản build** (tên số local/anonymous, accessor, bridge, field capture, thứ tự reflection);
- Hay **hợp đồng chính thức của ứng dụng** (interface, annotation, API, schema được công bố).

## 10. Câu hỏi tự kiểm tra

**1. Vì sao `Outer.class.getDeclaredClasses()` không thấy local class trong `work()`?** Vì `getDeclaredClasses()` dành cho member type khai báo trực tiếp. Điều đó không có nghĩa compiler không biên dịch local class.

**2. `Outer$A` và `Outer$B` chắc chắn cùng nest?** Không suy ra được chỉ từ tên. Dùng `isNestmateOf()` khi đã có hai đối tượng `Class<?>`.

**3. `Class.forName("pkg.Outer$Inner")` có sai không?** Không, nếu đó thực sự là binary name của member type có tên và có thể được nạp. Cách này khác việc đoán tên anonymous class `Outer$1`.

**4. Có nên bỏ mọi method synthetic khỏi công cụ phân tích?** Tùy mục đích. Công cụ làm tài liệu source-level có thể ẩn chúng; công cụ phân tích dispatch/bytecode có thể cần bridge methods.

**5. Có nên dùng `getSimpleName()` của anonymous class để tạo ID?** Không. Nó rỗng, và ngay cả `getName()` cũng không cung cấp một ID ứng dụng ổn định.

## 11. Tổng kết kiến thức

- Reflection cho biết cấu trúc class file/runtime; không phải toàn bộ cấu trúc đó đều do ứng dụng sở hữu.
- Member binary name được quy định, nhưng số của local/anonymous class, field/ accessor compiler sinh và tên triển khai lambda không phải hợp đồng nghiệp vụ.
- Member declaration, enclosing context và nestmate access là ba khái niệm riêng.
- Để ứng dụng bền vững qua nhiều bản build, hãy dựa vào **API, interface, annotation, schema hoặc registry do mình công bố**.

### Tài liệu chính thức

- [Java SE 17 — `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): đặc tả các phương thức phân loại, enclosing và nest.
- [JLS 17, §13.1 — Binary compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1): quy tắc tên nhị phân của member/local/anonymous class.
- [JVMS 17, §4.7.28–29](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): class-file attributes `NestHost` và `NestMembers`.
