# TypeNotPresentException, EnumConstantNotPresentException và lỗi thay đổi hợp đồng annotation trong Java

## 1. Bài toán: annotation từng biên dịch thành công nhưng nay đọc lại bị lỗi

Java annotation là **metadata được mã hóa vào class file** theo chính sách `@Retention`. Khi retention là `RUNTIME`, chương trình có thể lấy annotation qua reflection và gọi các phần tử (annotation elements), ví dụ `config.provider()`, `config.mode()` hoặc `config.level()`.

Rủi ro xuất hiện khi **class chứa annotation đã biên dịch với phiên bản thư viện A**, nhưng lúc chạy lại chỉ có **phiên bản thư viện B không tương thích**. Java có thể tải được class đã biên dịch và thậm chí có thể trả object đại diện cho annotation; tuy nhiên khi đọc một element, JVM/thư viện reflection không còn giải mã được dữ liệu cũ theo định nghĩa mới.

Hai lỗi trọng tâm:

- **`java.lang.TypeNotPresentException`**: annotation lưu tham chiếu tới một kiểu không còn được resolve tại thời điểm đọc metadata hoặc trong một ngữ cảnh tương tự. Với element kiểu `Class<?>`, ví dụ `provider = OldProvider.class`, nếu `OldProvider` không còn trong runtime, việc lấy `provider()` có thể ném lỗi này.
- **`java.lang.EnumConstantNotPresentException`**: metadata lưu tên một hằng enum nhưng kiểu enum đang có ở runtime **không chứa hằng đó**. Ví dụ annotation cũ lưu `Mode.LEGACY`, còn `Mode` mới chỉ có `BASIC`.

Các lỗi khác phản ánh **thay đổi hợp đồng của annotation type**:

- **`java.lang.annotation.AnnotationTypeMismatchException`**: giá trị được mã hóa trong class file **không tương thích với kiểu trả về mới** của một annotation element, chẳng hạn `int level()` đổi thành `String level()`.
- **`java.lang.annotation.IncompleteAnnotationException`**: định nghĩa annotation mới đòi hỏi một element **không có giá trị** trong metadata cũ và **không có default** để bù, ví dụ bổ sung `String owner();`.
- Ngoài ra còn có thể gặp `NoSuchMethodError` hoặc lỗi liên kết khác khi **code gọi một accessor đã đổi tên/đổi chữ ký nhị phân**, vốn không đồng nhất với lỗi giải mã giá trị annotation.

Điểm chung: **biên dịch thành công ở một thời điểm không bảo đảm metadata cũ luôn đọc được với các dependency ở thời điểm khác**. Bài học sẽ chỉ ra nguyên nhân, cách tái hiện bằng Java 17, điểm khác nhau giữa các exception và biện pháp kiểm thử khi phát hành thư viện.

## 2. Annotation element không phải một field Java bình thường

Ví dụ annotation định nghĩa:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Contract {
    Class<?> provider();
    Mode mode();
}
~~~

Đây là **đoạn khai báo minh họa**; cần có enum `Mode` và các khai báo liên quan để biên dịch một chương trình hoàn chỉnh.

Annotation element có cú pháp giống method không tham số, nhưng các giá trị `provider = SomeType.class` và `mode = Mode.LEGACY` được compiler mã hóa vào metadata của **nơi gắn annotation**, không trở thành instance field trên object nghiệp vụ.

Khi thực hiện:

~~~java
Contract contract = SomeClass.class.getAnnotation(Contract.class);
Class<?> type = contract.provider();
Mode mode = contract.mode();
~~~

chương trình đọc một **biểu diễn runtime** của annotation. Trên JDK thông dụng, việc giải mã các giá trị không thể resolve có thể được trì hoãn đến lúc gọi element tương ứng. Vì vậy, chỉ nhìn thấy `contract != null` **chưa chứng minh** tất cả các element đều hợp lệ.

Không được coi tính chất “thường ném khi gọi accessor” là cam kết rằng mọi implementation, mọi class loader và mọi dạng metadata lỗi sẽ luôn thất bại đúng tại một dòng cố định. Khi viết bộ quét metadata, phải xử lý lỗi trong **phạm vi cả thao tác tra cứu và đọc các element cần thiết**, rồi đưa ra chẩn đoán chính xác.

## 3. Phân biệt các nhóm lỗi

| Tình huống | Lỗi tiêu biểu | Nguyên nhân bản chất | Dữ liệu hữu ích khi chẩn đoán |
| --- | --- | --- | --- |
| Giá trị annotation kiểu `Class<?>` nhắc tới type không thể resolve | `TypeNotPresentException` | Tên kiểu còn trong annotation cũ nhưng type thiếu/không resolve được ở runtime | `typeName()`, `getCause()` |
| Giá trị annotation enum nhắc tới hằng không còn trong enum runtime | `EnumConstantNotPresentException` | Tên enum constant không khớp phiên bản hiện có | `enumType()`, `constantName()` |
| Kiểu trả về element đã thay đổi không tương thích với giá trị đã mã hóa | `AnnotationTypeMismatchException` | Stored value không còn phù hợp kiểu element | `element()`, `foundType()` |
| Thêm element bắt buộc mới, metadata cũ không mang giá trị | `IncompleteAnnotationException` | Không có stored value, cũng không có default | `annotationType()`, `elementName()` |
| Consumer cũ gọi chữ ký method element không còn trong annotation interface mới | `NoSuchMethodError` | Binary method descriptor thay đổi hoặc member bị bỏ | Tên/chữ ký accessor tại bytecode gọi |
| Class file annotation bị hỏng/không hợp lệ | `AnnotationFormatError` có thể xuất hiện | Metadata cấu trúc không hợp lệ; không chỉ là enum/type thay đổi | Stack trace, class file và bản build |

**Quan trọng:** `TypeNotPresentException` không đồng nghĩa với `ClassNotFoundException`. Lỗi thứ nhất là một runtime exception với ngữ nghĩa API về **kiểu được nhắc tên nhưng không hiện diện**; `ClassNotFoundException` là checked exception thường thấy ở những API như `Class.forName(...)`. Chúng có thể liên quan đến cùng type bị thiếu, nhưng điểm phát sinh và cách bắt lỗi không giống nhau.

Tương tự, `EnumConstantNotPresentException` **không phải** `IllegalArgumentException` do một lệnh tự gọi `Enum.valueOf` với chuỗi sai. Nó là exception chuyên biệt cho một enum constant không còn tương ứng khi runtime đọc một annotation element.

## 4. Thí nghiệm 1: tái hiện cùng lúc hai exception chính

Ta sẽ tạo **phiên bản V1** của một annotation và các kiểu liên quan:

- Annotation `@Contract` có `Class<?> provider()` và `Mode mode()`.
- Enum `Mode` có `BASIC`, `LEGACY`.
- Class `OldProvider` còn tồn tại khi biên dịch.
- `Annotated` gắn `@Contract(provider = OldProvider.class, mode = Mode.LEGACY)`.

Sau đó, tạo **phiên bản V2** của enum `Mode`, chỉ còn `BASIC`; mô phỏng deployment bị thiếu `OldProvider.class`. Class `Annotated.class` vẫn là bytecode đã biên dịch bằng V1. Đây là môi trường cố ý không đồng bộ phiên bản để tái hiện lỗi.

### 4.1. Cấu trúc nguồn

~~~text
src/
├── v1/
│   └── demo/
│       ├── Contract.java
│       ├── Mode.java
│       ├── OldProvider.java
│       ├── Annotated.java
│       └── Main.java
└── v2/
    └── demo/
        └── Mode.java
~~~

Không cần thư viện ngoài JDK. Những file có `public` type phải đúng tên với type công khai tương ứng.

### V1 — `src/v1/demo/Contract.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Contract {
    Class<?> provider();
    Mode mode();
}
~~~

`RUNTIME` là điều kiện để phương thức `getAnnotation(Contract.class)` nhìn thấy lần sử dụng annotation ở runtime. `@Target(TYPE)` cho phép đặt annotation trên class.

### V1 — `src/v1/demo/Mode.java`

~~~java
package demo;

public enum Mode {
    BASIC,
    LEGACY
}
~~~

### V1 — `src/v1/demo/OldProvider.java`

~~~java
package demo;

public final class OldProvider {
}
~~~

Lớp `OldProvider` không cần có method nào, vì thí nghiệm chỉ dùng **class literal** `OldProvider.class` trong annotation. Compiler xác nhận type tồn tại khi biên dịch nguồn.

### V1 — `src/v1/demo/Annotated.java`

~~~java
package demo;

@Contract(provider = OldProvider.class, mode = Mode.LEGACY)
public final class Annotated {
}
~~~

Trong `Annotated.class` có metadata chứa tham chiếu tới type `demo.OldProvider` và tên enum constant `LEGACY`, theo định nghĩa ở thời điểm biên dịch.

### V1 — `src/v1/demo/Main.java`

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        Contract c = Annotated.class.getAnnotation(Contract.class);
        System.out.println("annotation present: " + (c != null));

        try {
            System.out.println("provider: " + c.provider().getName());
        } catch (TypeNotPresentException e) {
            System.out.println("missing type: " + e.typeName());
        }

        try {
            System.out.println("mode: " + c.mode());
        } catch (EnumConstantNotPresentException e) {
            System.out.println("missing enum: "
                    + e.enumType().getName() + "." + e.constantName());
        }
    }
}
~~~

Trong ví dụ, mỗi lần đọc element được đặt trong một `try/catch` riêng. Nhờ đó người học nhìn thấy **cả hai lỗi**, thay vì lỗi đầu làm chương trình kết thúc và che khuất lỗi sau. Một chương trình sản xuất phải có chính sách xử lý nghiêm hơn; ví dụ chỉ in để chứng minh hành vi API.

### V2 — `src/v2/demo/Mode.java`

~~~java
package demo;

public enum Mode {
    BASIC
}
~~~

Phiên bản V2 **giữ nguyên tên binary của enum `demo.Mode`** nhưng bỏ hằng `LEGACY`. Điều này khác hoàn toàn với việc xóa cả `Mode.class`: ở đây type enum vẫn load được, chỉ có constant được metadata cũ nhắc tới không còn.

### 4.2. Biên dịch Java 17 và chạy bản đồng bộ V1

Dưới đây là lệnh **Bash trên Linux/macOS** khi đang ở thư mục có `src`. Với PowerShell, sử dụng `New-Item -ItemType Directory -Force` và `Copy-Item` cho các thao tác tạo thư mục/sao chép thay cho `mkdir -p`/`cp`; các lệnh `javac` và `java` giữ nguyên.

~~~bash
mkdir -p build/v1 build/v2 build/runtime/demo

javac --release 17 -d build/v1 src/v1/demo/*.java
javac --release 17 -d build/v2 src/v2/demo/Mode.java

java -cp build/v1 demo.Main
~~~

**Stdout khi chạy đồng bộ V1:**

~~~text
annotation present: true
provider: demo.OldProvider
mode: LEGACY
~~~

Ở phiên bản V1 đầy đủ, cả kiểu `demo.OldProvider` và enum `Mode.LEGACY` đều hiện diện; việc đọc hai element thành công.

### 4.3. Lắp runtime không tương thích, không biên dịch lại Annotated

Sao chép chính xác **ba class V1** cần để tra cứu annotation và chạy chương trình; không sao chép `OldProvider.class` và không sao chép `Mode.class` V1. Sau đó sao chép `Mode.class` từ V2:

~~~bash
cp build/v1/demo/Contract.class build/runtime/demo/
cp build/v1/demo/Annotated.class build/runtime/demo/
cp build/v1/demo/Main.class build/runtime/demo/
cp build/v2/demo/Mode.class build/runtime/demo/

java -cp build/runtime demo.Main
~~~

**Stdout chính xác của runtime đã cố tình thay đổi hợp đồng:**

~~~text
annotation present: true
missing type: demo.OldProvider
missing enum: demo.Mode.LEGACY
~~~

Đây là kết quả đã được biên dịch bằng `javac --release 17` và chạy thử trên JDK hỗ trợ Java 17.

### 4.4. Giải thích vì sao từng lỗi xuất hiện

**Dòng 1 — annotation present: true**

`Annotated.class` còn `@Contract` có retention `RUNTIME`; kiểu annotation `demo.Contract` cũng có mặt. Runtime có thể trả về annotation representation. Điều đó **chưa đảm bảo** mọi giá trị bên trong có thể resolve.

**Dòng 2 — missing type: demo.OldProvider**

Trong metadata, element `provider` là class literal của `OldProvider`. Nhưng ta không đưa `OldProvider.class` vào `build/runtime`. Khi `c.provider()` cần trả `Class<?>`, runtime phải resolve tên class đã lưu, không tìm được và ném `TypeNotPresentException`. `e.typeName()` giúp ghi nhận đúng kiểu bị thiếu.

**Dòng 3 — missing enum: demo.Mode.LEGACY**

`c.mode()` phải trả một giá trị `Mode`. Runtime load được `demo.Mode` từ V2, nhưng enum này chỉ có `BASIC`. Tên constant `LEGACY` có trong annotation cũ không còn tương ứng, nên runtime ném `EnumConstantNotPresentException`. `e.enumType()` và `e.constantName()` cung cấp thông tin enum type và constant để chẩn đoán.

**Điểm cần nhớ:** hai lỗi khác nhau vì một bên thiếu **class type**, bên kia thiếu **enum constant trong một enum type vẫn có thể nạp được**. Chỉ xem `getAnnotation(...) != null` không đủ làm phép kiểm thử tương thích.

## 5. Thí nghiệm 2: thay đổi chính annotation type

Một lỗi phổ biến khác đến từ thay đổi định nghĩa `@interface` thay vì thay enum hay dependency. Giả sử V1:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Config {
    int level();
}
~~~

Một class V1 dùng:

~~~java
@Config(level = 7)
public class OldAnnotated {}
~~~

Sau khi phát hành, thư viện V2 đổi contract thành:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Config {
    String level();
    String owner();
}
~~~

Các khối trên là **minh họa so sánh hai phiên bản**, chưa đủ imports và package để chạy độc lập. Ta sẽ làm rõ bằng fixture Java 17 hoàn chỉnh:

- `int level()` đổi thành `String level()`: giá trị `7` còn lưu trong class file cũ có kiểu không khớp; truy xuất bằng accessor mới có thể ném `AnnotationTypeMismatchException`.
- `String owner()` là element mới **bắt buộc**, không có `default`; `OldAnnotated.class` V1 không lưu owner, nên gọi `owner()` có thể ném `IncompleteAnnotationException`.

### 5.1. Tệp V1

**`src/v1/demo/Config.java`** (đây là fixture **độc lập với thí nghiệm 1**; dùng thư mục build khác nếu chạy cả hai):

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Config {
    int level();
}
~~~

**`src/v1/demo/OldAnnotated.java`**:

~~~java
package demo;

@Config(level = 7)
public final class OldAnnotated {
}
~~~

### 5.2. Tệp V2 và chương trình kiểm tra

**`src/v2/demo/Config.java`**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Config {
    String level();
    String owner();
}
~~~

**`src/v2/demo/Probe.java`**:

~~~java
package demo;

import java.lang.annotation.AnnotationTypeMismatchException;
import java.lang.annotation.IncompleteAnnotationException;

public final class Probe {
    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> old = Class.forName("demo.OldAnnotated");
        Config config = old.getAnnotation(Config.class);
        System.out.println("present: " + (config != null));

        try {
            System.out.println("level: " + config.level());
        } catch (AnnotationTypeMismatchException e) {
            System.out.println("mismatch element: "
                    + e.element().getName());
        }

        try {
            System.out.println("owner: " + config.owner());
        } catch (IncompleteAnnotationException e) {
            System.out.println("incomplete element: "
                    + e.elementName());
        }
    }
}
~~~

`Probe` được biên dịch **với Config V2**; `OldAnnotated.class` được giữ nguyên **từ V1**. Ta chủ động dùng `Class.forName("demo.OldAnnotated")` thay vì tham chiếu source V1 trong quá trình biên dịch V2, rồi tạo runtime chỉ chứa đúng các class cần thiết.

### 5.3. Biên dịch, lắp runtime và chạy

Dùng một thư mục làm việc mới cho thí nghiệm 2, với cấu trúc `src/v1/demo` và `src/v2/demo` của chính thí nghiệm này:

~~~bash
mkdir -p build/v1 build/v2 build/runtime/demo

javac --release 17 -d build/v1 \
    src/v1/demo/Config.java src/v1/demo/OldAnnotated.java

javac --release 17 -d build/v2 \
    src/v2/demo/Config.java src/v2/demo/Probe.java

cp build/v1/demo/OldAnnotated.class build/runtime/demo/
cp build/v2/demo/Config.class build/runtime/demo/
cp build/v2/demo/Probe.class build/runtime/demo/

java -cp build/runtime demo.Probe
~~~

**Stdout đã được kiểm chứng:**

~~~text
present: true
mismatch element: level
incomplete element: owner
~~~

Đây là thí nghiệm tạo **hai loại lỗi khác nhau** với cùng một annotation representation runtime: stored value `level = 7` không còn khớp `String`, còn `owner` là element hoàn toàn mới không có default.

Nếu thay `String owner();` ở V2 bằng:

~~~java
String owner() default "unknown";
~~~

thì việc thiếu owner trong metadata V1 được giải quyết nhờ default mới và không nhất thiết gây `IncompleteAnnotationException`. Tuy nhiên, **ý nghĩa mặc định** `"unknown"` phải được thiết kế cẩn thận; “không còn exception” không có nghĩa là nâng cấp đã giữ nguyên ý nghĩa nghiệp vụ.

## 6. AnnotationTypeMismatchException khác NoSuchMethodError ở đâu?

Thay đổi `int level()` thành `String level()` có hai mặt:

1. **Metadata cũ:** trong `OldAnnotated.class`, annotation element `level` có giá trị primitive kiểu int. Khi runtime đọc nó bằng định nghĩa `Config` V2 có method `String level()`, dữ liệu không tương thích, từ đó có thể ném `AnnotationTypeMismatchException`.
2. **Bytecode consumer cũ:** một class đã biên dịch để gọi `Config.level():int` vẫn tham chiếu **chữ ký JVM cũ**. Nếu chạy class consumer ấy với annotation interface chỉ còn `String level()`, JVM có thể báo `NoSuchMethodError` vì descriptor cũ không còn. Đây là lỗi **binary linkage**, không phải việc annotation proxy giải mã stored value.

Thí nghiệm 2 cố ý **biên dịch `Probe` với V2** để minh họa nhóm (1) rõ ràng. Nếu kiểm thử binary compatibility cho ứng dụng lớn, phải kiểm tra **cả các class đã gắn annotation** và **các consumer/processor đã biên dịch gọi annotation element**. Chỉ thử biên dịch lại một chương trình nhỏ với API mới không đủ chứng minh toàn bộ hệ thống tương thích nhị phân.

Đổi tên `level()` thành `priority()` cũng là thay đổi API lớn: mã nguồn gọi `level()` cũ sẽ không biên dịch lại, còn binary consumer cũ có thể gặp lỗi liên kết. Nếu class file đã gắn annotation có giá trị `level` nhưng định nghĩa mới chỉ có `priority` bắt buộc, khi đọc `priority` có thể gặp `IncompleteAnnotationException`.

## 7. Điều gì xảy ra khi thêm, xóa và sửa default element?

Thay đổi annotation type cần được xem như thay đổi API công khai, bởi mọi lần dùng annotation được compiler kiểm tra và ghi vào class file.

| Thay đổi định nghĩa annotation | Đối với source dùng annotation khi biên dịch lại | Đối với annotation đã biên dịch từ trước |
| --- | --- | --- |
| Thêm element `String owner();` (không default) | Nơi dùng cũ phải cung cấp `owner`, nếu không compiler báo lỗi | Truy cập `owner()` có thể gây `IncompleteAnnotationException` |
| Thêm element `String owner() default "unknown";` | Source cũ thường vẫn biên dịch | Runtime có thể dùng default mới, nhưng có thể đổi ý nghĩa |
| Đổi default từ `"A"` sang `"B"` | Source không chỉ định element vẫn hợp lệ | Giá trị quan sát được khi truy cập có thể chuyển theo định nghĩa annotation type hiện dùng |
| Đổi kiểu element, như `int` → `String` | Mọi nơi dùng phải tuân kiểu mới | Giá trị cũ có thể gây `AnnotationTypeMismatchException`; consumer cũ có thể gặp `NoSuchMethodError` |
| Xóa hoặc đổi tên element | Lần dùng source chỉ định element cũ thường không còn hợp lệ | Consumer cũ có thể bị lỗi liên kết; giá trị cũ có thể bị bỏ qua tùy phép đọc và element mới |
| Bỏ/đổi tên class literal trong element | Source cần type thay thế | `TypeNotPresentException` khi đọc type cũ không resolve được |
| Xóa/đổi tên hằng enum trong element | Source cần dùng constant hợp lệ | `EnumConstantNotPresentException` khi đọc constant cũ |
| Đổi `@Retention` `RUNTIME` → `CLASS` | Source gắn annotation vẫn có thể biên dịch | Cần xem bytecode đã biên dịch; các lần dùng mới không còn khả dụng cho reflection runtime |
| Thu hẹp `@Target` | Những vị trí gắn không còn hợp lệ khi biên dịch lại | Class file cũ không được tự viết lại; phải kiểm thử tool tiêu thụ |
| Đổi package/tên annotation type | Cần cập nhật import và lần dùng | Bytecode cũ vẫn nhắc đến tên type trước đó; có thể mất metadata khi tra cứu type mới |

**Quan trọng với default:** Annotation default được lưu trong **định nghĩa annotation type**, không phải luôn sao chép thành giá trị tường minh ở mọi lần dùng. Bởi vậy thay đổi default có thể ảnh hưởng những class đã biên dịch mà không ghi rõ element. Đây là một nguồn **thay đổi hành vi im lặng** dù không phát sinh exception.

Đừng xem “binary linkage còn chạy được” là đồng nghĩa “semantic compatibility được giữ nguyên”. Ví dụ đổi default của một permission hay cờ policy có thể gây hậu quả nghiêm trọng hơn một exception dễ phát hiện.

## 8. Vì sao exception có thể xuất hiện muộn?

Java Reflection API thông thường trả một biểu diễn annotation có các element mà chương trình có thể gọi. Trong nhiều trường hợp, dữ liệu lỗi chỉ được phát hiện khi element đó thực sự được truy xuất:

~~~java
Contract contract = Annotated.class.getAnnotation(Contract.class);
System.out.println(contract != null); // Có thể vẫn là true
contract.provider();                   // Có thể ném TypeNotPresentException
contract.mode();                       // Có thể ném EnumConstantNotPresentException
~~~

Đây là đoạn minh họa dựa trên thí nghiệm 1, **không phải chương trình standalone**.

Có ba hệ quả khi kiểm thử:

- Test chỉ gọi `isAnnotationPresent(...)` hoặc `getAnnotation(...)` có thể **không bao phủ tất cả element values**.
- Test chỉ gọi một element thành công có thể bỏ qua lỗi ở element khác.
- Việc exception xuất hiện không nhất thiết tại thời điểm JVM load class nghiệp vụ khiến lỗi trở nên khó liên hệ với lần nâng cấp thư viện trước đó.

Nếu code có nhiệm vụ validate toàn bộ metadata, cần truy cập **những element thật sự thuộc contract** và kiểm tra các giá trị/kiểu cần thiết; không đơn thuần kiểm tra annotation tồn tại.

Không khẳng định mọi lỗi đều trì hoãn: metadata malformed, type annotation resolution, class loading và các đường đi reflection cụ thể có thể gây lỗi tại những thời điểm khác. Hãy xử lý exceptions ở ranh giới scanner/framework phù hợp.

## 9. Chiến lược chẩn đoán trong ứng dụng thật

Khi gặp một trong hai exception chính, quy trình hữu ích là:

1. **Ghi lại annotated element đang đọc**: fully qualified class name, field/method/constructor, annotation type và element đang truy xuất. Không chỉ log một stack trace không có bối cảnh.
2. **Ghi phiên bản của JAR và class loader**: bản annotation API, enum, type tham chiếu và class file đã được gắn annotation có thể đến từ những artifact khác nhau.
3. **Xem giá trị trong bytecode** bằng `javap -v` (hoặc bytecode reader tương đương) trên **class đã gắn annotation**. Tìm `RuntimeVisibleAnnotations` với annotation type và giá trị `Class`/enum đã lưu.
4. **So sánh API ở compile time và runtime**. Nếu dependency class bị xóa khỏi runtime, bổ sung đúng dependency hoặc biên dịch lại với type mới. Nếu enum constant bị xóa, cân nhắc giữ constant cũ hoặc di chuyển metadata sang constant mới rồi biên dịch lại các class áp dụng.
5. **Đối với `AnnotationTypeMismatchException`**, so sánh kiểu element trước và sau; đừng chỉ tìm tên element. Đối với `IncompleteAnnotationException`, kiểm tra phần tử mới có default hợp lệ hay không.
6. **Kiểm tra dependency conflicts**: nhiều phiên bản cùng thư viện, shading/relocation, fat JAR, classpath order và module path có thể khiến runtime lấy định nghĩa khác dự kiến.
7. **Kiểm thử với artifact đã đóng gói cuối cùng**. Không chỉ chạy test trên môi trường IDE nếu ứng dụng triển khai bằng một tập JAR khác.

Ví dụ các lệnh hỗ trợ trên JDK:

~~~bash
javap -v -classpath build/v1 demo.Annotated
javap -p -classpath build/v1 demo.Contract
javap -p -classpath build/v2 demo.Mode
~~~

Lệnh thứ nhất giúp xem metadata annotation trên `Annotated.class`; lệnh thứ hai xem chữ ký annotation element ở API V1; lệnh thứ ba xem enum runtime V2. `javap` không phải trình sửa bytecode; nó dùng để **quan sát** điều compiler đã tạo.

Nếu dự án dùng named modules, có thể cần thay `-classpath` bằng cách xác định đúng module path/module name; nguyên tắc vẫn là **quan sát chính class file và phiên bản thực sự được runtime nạp**.

## 10. Xử lý lỗi trong một framework hoặc scanner

Một bộ quét metadata có thể muốn phát chẩn đoán rõ thay vì làm ứng dụng chết bằng một exception không có bối cảnh. Ví dụ (đoạn minh họa trong ứng dụng đã định nghĩa `Contract` và `Annotated`):

~~~java
try {
    Contract c = Annotated.class.getAnnotation(Contract.class);
    if (c == null) {
        throw new IllegalStateException("Missing @Contract");
    }
    Class<?> provider = c.provider();
    Mode mode = c.mode();
    System.out.println(provider.getName() + ":" + mode.name());
} catch (TypeNotPresentException e) {
    throw new IllegalStateException(
            "Missing provider type in @Contract: " + e.typeName(), e);
} catch (EnumConstantNotPresentException e) {
    throw new IllegalStateException(
            "Missing enum constant in @Contract: "
                    + e.enumType().getName() + "." + e.constantName(), e);
}
~~~

Đoạn này là **mã minh họa**, không độc lập. Trong runtime bị lệch phiên bản của thí nghiệm 1, lỗi đầu sẽ khiến code ném `IllegalStateException`; muốn tổng hợp mọi lỗi metadata, cần kiểm tra từng element riêng biệt giống `Main` ở thí nghiệm.

Một số lưu ý:

- Nếu metadata điều khiển **phân quyền, validation, routing hoặc bảo mật**, nên **fail closed** khi giá trị cần thiết không đọc được. Đừng mặc định một permission bị lỗi thành “không cần quyền”.
- Không bắt một `Exception` quá rộng rồi bỏ qua, vì sẽ che nguyên nhân và có thể để framework chạy với cấu hình sai.
- Đừng dùng `null` làm giá trị dự phòng cho annotation element: Java annotation không cho literal `null` và ý nghĩa lỗi metadata cũng không nên được biến thành một giá trị thông thường.
- Nếu chọn phương án tương thích ngược, lập tài liệu: giữ type cũ bao lâu, mapping enum cũ sang mới như thế nào và những class nào phải biên dịch lại.
- Tránh ghi các giá trị bí mật trong annotation vì retention `CLASS`/`RUNTIME` có thể khiến chúng hiện trong class file và công cụ phân tích.

Đối với `AnnotationTypeMismatchException` và `IncompleteAnnotationException`, một scanner có thể phát thông báo bổ sung dựa trên `element()`/`elementName()`. Tuy nhiên, các exception này thường chỉ ra **lỗi đóng gói/deployment hoặc hợp đồng API**, không phải lỗi dữ liệu mà người dùng cuối có thể tự sửa lúc chạy.

## 11. Hướng sửa từng tình huống

### 11.1. Khi Class<?> element tham chiếu type không còn

Nếu một annotation cũ chứa `OldProvider.class`, có thể:

1. **Khôi phục binary type cũ** trong runtime nếu vẫn có thể duy trì tương thích và nó an toàn để dùng.
2. **Chuyển những class đã gắn annotation sang type mới** trong source, rồi biên dịch lại chúng.
3. Nếu đổi package/class name, dùng chính sách migration rõ ràng thay vì chỉ đổi JAR chứa annotation type. Bytecode của annotated class cũ vẫn giữ tên class literal cũ.
4. Kiểm tra class loader/module visibility nếu type vật lý tồn tại nhưng không thể resolve từ ngữ cảnh đọc annotation.

Không nên chỉ thêm một dependency bất kỳ trùng simple name: JVM nhận diện class bằng **binary name và class loader**, không bằng tên file hiển thị hoặc simple name.

### 11.2. Khi enum constant bị đổi tên hoặc xóa

Ví dụ V1 `Mode.LEGACY` và V2 chỉ có `Mode.BASIC`.

- **Giữ `LEGACY`** trong enum V2 (có thể đánh dấu deprecated) là một biện pháp tương thích khi giá trị đó vẫn cần được giải mã.
- **Biên dịch lại mọi class đã gắn annotation** để chỉ còn dùng constant hợp lệ là giải pháp trực tiếp, nhưng phải xác định hết những artifact sử dụng dữ liệu cũ.
- **Không mong runtime tự map** `LEGACY` thành `BASIC`: annotation metadata lưu tên constant, Java không có alias enum tự động.
- Nếu logic mới có ngữ nghĩa khác với constant cũ, tạo lớp chuyển đổi/compatibility policy ở consumer một cách tường minh, không âm thầm xem hai giá trị là một.

Thay đổi **thứ tự khai báo** constants trong enum không giống xóa/đổi tên constant. Annotation lưu tên constant theo mô hình class file, vì vậy không suy luận rằng chỉ đổi thứ tự enum là nguyên nhân trực tiếp của `EnumConstantNotPresentException`.

### 11.3. Khi thêm phần tử bắt buộc hoặc đổi kiểu trả về

- Để tương thích với annotated classes cũ khi thêm element, cân nhắc **`default` có ý nghĩa** thay vì yêu cầu tất cả class cũ có dữ liệu chưa từng được mã hóa.
- Nếu thay đổi kiểu trả về của element, thường nên **tạo annotation API/element mới** hoặc có kế hoạch chuyển đổi/biên dịch lại toàn bộ consumers và annotated classes, thay vì giả định JVM tự chuyển `int` sang `String`.
- Đừng dùng default chỉ để giấu lỗi hợp đồng. Với thông tin nhạy cảm như permission, owner bắt buộc hoặc policy, default tùy tiện có thể tạo hành vi sai.
- Đừng đổi default hiện có mà không kiểm tra impact đối với annotated class vốn không chỉ định element; giá trị effective lúc chạy có thể đổi mà không báo lỗi.

## 12. Phân biệt với các lỗi annotation khác

Trong dự án lớn còn một số tình huống liên quan nhưng khác gốc:

**`AnnotationFormatError`:** metadata annotation/class file không hợp lệ theo định dạng mà runtime xử lý. Đây là một `Error` chuyên biệt, không phải mọi lỗi đọc enum/type. Không được dùng catch-all `Error` để giả vờ tiếp tục với dữ liệu không đáng tin.

**`MirroredTypeException` trong annotation processor:** đây là exception thuộc `javax.lang.model.type`, có thể xảy ra khi processor ở **compile time** truy cập element kiểu `Class<?>` qua typed annotation proxy và compiler trả một `TypeMirror` thay vì class runtime. Nó **khác `TypeNotPresentException`** trong bối cảnh class không resolve lúc runtime. Ở processor, cách tổng quát hơn là dùng `AnnotationMirror`/`AnnotationValue` hoặc `TypeMirror` theo compiler model.

**`NoClassDefFoundError`:** có thể xuất hiện khi JVM không tải được một class cần thiết trong quá trình liên kết/khởi tạo hoặc đường đi dùng class khác. Nó không đồng nghĩa rằng mọi class literal được lưu trong annotation đều ném lỗi này. Thí nghiệm 1 cho thấy khi đọc annotation element kiểu `Class<?>` bị thiếu, exception chuyên biệt xuất hiện là `TypeNotPresentException`.

**`IncompleteAnnotationException`:** chỉ ra phần tử bắt buộc bị thiếu trong annotation representation. Nó không giống compile-time error khi source mới viết thiếu một element; compile-time error xảy ra trước khi tạo bytecode, còn thí nghiệm 2 chứng minh lỗi ở runtime vì bytecode cũ gặp định nghĩa mới.

**`AnnotationTypeMismatchException`:** chỉ ra stored annotation value có kiểu không phù hợp với annotation element method hiện tại, không phải lỗi ép kiểu Java thông thường do người dùng viết cast sai.

Nhờ phân biệt **compiler error**, **annotation decoding error** và **linkage error**, ta tránh áp dụng sai cách sửa.

## 13. Quy trình kiểm thử thay đổi hợp đồng annotation

Trước khi phát hành một phiên bản API mới chứa `@interface` hoặc enum/type dùng trong annotation, nên có ít nhất bốn nhóm test.

### 13.1. Test source compatibility

Biên dịch lại một project mẫu sử dụng annotation từ phiên bản trước **với API phiên bản mới**. Kiểm tra những element mới bắt buộc, kiểu giá trị đổi, package/type name và target bị thu hẹp. Đây là bước dễ phát hiện sai khi source được biên dịch lại.

### 13.2. Test binary compatibility

**Giữ nguyên bytecode annotated class từ phiên bản trước**, nhưng chạy bằng API/runtime version mới. Đây là test quan trọng mà việc “clean build toàn bộ” có thể vô tình bỏ sót: mọi metadata cũ đã được compiler mã hóa dựa trên hợp đồng cũ.

Thí nghiệm 1 là phép thử rõ ràng: giữ `Annotated.class` V1, bỏ `OldProvider.class` và thay `Mode.class` bằng bản V2. Thí nghiệm 2 giữ `OldAnnotated.class` V1, thay annotation type `Config` bằng V2.

### 13.3. Test tất cả annotation elements, không chỉ presence

Ví dụ một bộ kiểm tra:

~~~java
Contract c = Annotated.class.getAnnotation(Contract.class);
if (c == null) {
    throw new IllegalStateException("@Contract missing");
}
c.provider();
c.mode();
~~~

Đây là ví dụ minh họa, không phải test hợp lệ trong runtime đã cố ý làm lỗi. Nó diễn tả yêu cầu **phải chạm tới tất cả element quan trọng** để tìm lỗi compatibility. Nếu chỉ dùng `isAnnotationPresent`, test có thể qua dù một element sẽ hỏng khi framework xử lý thực tế.

### 13.4. Test hành vi nghiệp vụ và defaults

Trường hợp không ném exception vẫn có thể sai: đổi `@RequiresPermission` default, thay enum có cùng tên nhưng đổi ý nghĩa, hoặc đổi policy kết hợp annotation. Do đó phải kiểm tra **giá trị thực tế**, hành vi consumer và chính sách fail-safe, không chỉ “mã còn chạy”.

Một bảng đánh giá trước khi release:

| Thay đổi | Source compile test | Old-bytecode runtime test | Semantic test |
| --- | --- | --- | --- |
| Xóa một provider class | Kiểm tra source annotation references | Đọc `Class<?>` element từ class cũ | Kiểm tra fallback/migration |
| Xóa enum constant | Biên dịch lại source dùng constant | Đọc enum element từ class cũ | Đảm bảo chuyển nghĩa đúng |
| Đổi kiểu element | Kiểm tra source calls/uses | Đọc stored value bằng API mới; thử consumer cũ | Đánh giá biểu diễn mới |
| Thêm element bắt buộc | Compiler báo chỗ thiếu | Đọc element trên class cũ | Chọn default nếu an toàn |
| Đổi default | Source có thể vẫn biên dịch | Kiểm tra effective value với class cũ | Đánh giá thay đổi policy |
| Đổi retention/target | Compiler và metadata của build mới | Xem cách đọc class file cũ | Xác nhận công cụ vẫn hoạt động |

## 14. Bài tập mở rộng

**Bài tập A — chỉ gây TypeNotPresentException.** Giữ enum V1 có `LEGACY` trong runtime nhưng không cung cấp `OldProvider.class`. Kỳ vọng `c.provider()` lỗi, còn `c.mode()` vẫn thành công.

**Bài tập B — chỉ gây EnumConstantNotPresentException.** Giữ `OldProvider.class` trong runtime nhưng thay `Mode.class` bằng V2 không có `LEGACY`. Kỳ vọng `c.provider()` trả type, còn `c.mode()` lỗi. Có thể dùng thay đổi tập file được sao chép sang runtime để tạo hai biến thể.

**Bài tập C — bổ sung default.** Trong thí nghiệm 2, sửa element mới thành `String owner() default "unknown";`, biên dịch lại V2 và giữ nguyên `OldAnnotated.class` V1. Kiểm tra rằng `owner()` có thể dùng default, trong khi `level()` vẫn không khớp kiểu. Đây là sự phân tách rõ hai loại lỗi.

**Bài tập D — giữ nguyên kiểu element nhưng đổi default.** Dùng annotation `@Limit(max = 10)` trên một class và annotation `@Limit` không truyền giá trị trên class khác; thay default `max()` ở phiên bản mới. So sánh class có giá trị tường minh và class dùng default. Đoạn `@Limit` chỉ là ý tưởng bài tập; phải tự định nghĩa `@interface Limit` với `int max() default ...` trước khi biên dịch.

**Bài tập E — kiểm tra consumer cũ.** Biên dịch chương trình gọi `Config.level():int` bằng API V1, sau đó thay `Config` bằng API V2 trả `String` mà không biên dịch lại chương trình gọi. Quan sát khác biệt giữa lỗi liên kết method descriptor và lỗi stored annotation value. Không dùng kết luận từ `Probe` V2 để khẳng định consumer V1 chắc chắn ném cùng `AnnotationTypeMismatchException`.

**Bài tập F — kiểm tra với javap.** Dùng `javap -v -classpath build/v1 demo.Annotated` để xác định annotation `Contract` có stored type `demo.OldProvider` và constant `LEGACY`; dùng `javap -p` trên enum của V2 để đối chiếu danh sách constant thực tế.

## 15. Checklist triển khai an toàn

- [ ] Xem annotation type, mọi element method, enum và class literals được dùng như **một hợp đồng có phiên bản**.
- [ ] Giữ `@Retention(RUNTIME)` nếu consumer cần reflection và xác định đúng `@Target` cho nơi gắn.
- [ ] Tránh xóa/đổi tên Java type hoặc enum constants vẫn được class file cũ dùng trong annotation.
- [ ] Khi thêm element bắt buộc, đánh giá `default` có ý nghĩa và impact tới source/binary compatibility.
- [ ] Khi đổi kiểu hoặc tên element, có kế hoạch **migrate** cả annotated classes và consumers.
- [ ] Dùng `javap -v` trên **class được gắn annotation**, không chỉ trên class định nghĩa annotation type.
- [ ] Kiểm tra classpath/module path và **bản binary thực sự được deploy**, tránh phiên bản trộn.
- [ ] Test cả chương trình với old bytecode + new dependency, không chỉ clean compile bằng version mới.
- [ ] Đọc **từng annotation element quan trọng** trong test, không chỉ kiểm tra annotation có mặt.
- [ ] Khi scanner gặp metadata lỗi, log type/element/version và fail-safe theo chính sách, không bỏ qua lỗi có thể ảnh hưởng phân quyền.
- [ ] Kiểm tra thay đổi **ngữ nghĩa default** ngay cả khi không có exception.
- [ ] Tách riêng lỗi compile time, runtime annotation decoding và binary linkage trong báo cáo sự cố.

**Ghi nhớ:** `TypeNotPresentException` báo một kiểu được ghi trong annotation không resolve được; `EnumConstantNotPresentException` báo một enum constant được ghi trong annotation không còn ở runtime. Khi hợp đồng annotation thay đổi, còn có `AnnotationTypeMismatchException` và `IncompleteAnnotationException`. Các exception này có thể chỉ xuất hiện **khi đọc element**, vì thế kiểm thử tính tương thích phải giữ **bytecode cũ**, cung cấp **dependency mới** và truy xuất **mọi element có ý nghĩa**, thay vì chỉ xác nhận annotation hiện diện.
