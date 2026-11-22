# Tiến hóa hợp đồng annotation trong Java: thêm phần tử, đổi kiểu và thay đổi mặc định

## 1. Annotation là hợp đồng công khai, không chỉ là cú pháp @

Một annotation interface (`@interface`) khai báo **tập phần tử (elements)** mà code hoặc công cụ khác có thể cung cấp và đọc. Ví dụ:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Rule {
    String name();
    int retries() default 2;
    String mode() default "safe";
}
~~~

Code sử dụng annotation:

~~~java
@Rule(name = "payment", mode = "strict")
class PaymentService {}
~~~

Hợp đồng của `Rule` bao gồm nhiều thành phần:

- **Tên và kiểu của các phần tử:** `name()` trả `String`, `retries()` trả `int`, `mode()` trả `String`.
- **Phần tử bắt buộc hay tùy chọn:** `name()` không có `default` nên nơi sử dụng phải cấp giá trị; `retries()` và `mode()` có giá trị mặc định.
- **Giá trị mặc định và ý nghĩa:** `2` có thể biểu thị số lần thử lại; `"safe"` biểu thị chính sách mặc định do thư viện định nghĩa.
- **`@Target` / `@Retention`:** được phép đặt annotation ở đâu, có thể thấy qua reflection lúc chạy hay không.
- **Cách code sử dụng metadata diễn giải nó:** annotation processor, validator, serializer, framework DI, runtime reflection hoặc công cụ build có thể đọc phần tử và thực hiện logic riêng.

Do đó, việc thay đổi định nghĩa `@interface Rule` khi một thư viện đã được sử dụng giống **thay đổi API công khai**. Một thay đổi có thể giữ code cũ biên dịch được nhưng khiến hành vi runtime đổi, hoặc khiến một class file được tạo từ phiên bản cũ không còn đọc metadata đúng khi kết hợp với annotation type phiên bản mới.

Bài này tập trung vào **ba thao tác tiến hóa chính**:

1. **Thêm phần tử**: thêm `int timeout()` hoặc `int timeout() default 30`.
2. **Đổi kiểu phần tử**: `String mode()` thành `Mode mode()`, `int retry()` thành `long retry()`, hoặc `String tag()` thành `String[] tags()`.
3. **Thay đổi giá trị mặc định**: `retries() default 2` thành `retries() default 5`.

Mục tiêu là phân biệt **tương thích mã nguồn, tương thích liên kết binary, khả năng đọc annotation cũ và tương thích ngữ nghĩa** để chọn cách nâng phiên bản an toàn.

## 2. Ba tầng tương thích cần xem riêng

| Tầng | Câu hỏi phải trả lời | Ví dụ phát hiện lỗi |
|---|---|---|
| **Source compatibility** | Source đang dùng `@Rule(...)` có biên dịch lại với annotation type mới không? | Thêm phần tử mới không có `default` khiến chỗ dùng cũ thiếu argument |
| **Binary/linkage compatibility** | `.class` của client/library đã biên dịch có liên kết được với API mới không? | Caller cũ gọi method annotation theo descriptor cũ có thể ném `NoSuchMethodError` nếu kiểu trả về bị đổi |
| **Runtime metadata compatibility** | Khi đọc metadata đã lưu trong class file cũ, giá trị và kiểu có còn phù hợp với annotation interface mới? | `IncompleteAnnotationException` hoặc `AnnotationTypeMismatchException` |
| **Behavioral/semantic compatibility** | Dù chạy được, chính sách thực tế có thay đổi không? | Đổi `default 2` thành `default 5` làm các client không chỉ định giá trị bắt đầu retry 5 lần |

Các tầng có thể cho kết quả khác nhau. **“Không có lỗi biên dịch” không đồng nghĩa “nâng cấp an toàn”.** Ví dụ thay giá trị mặc định giữ nguyên method signature, nhưng làm framework đọc annotation và đổi hành vi mà không cần biên dịch lại client.

**Cẩn thận với từ “binary compatible”.** Một thay đổi của annotation interface có thể được phân loại theo quy tắc binary compatibility của Java, nhưng vẫn gây exception khi **đọc một phần tử annotation được lưu ở phiên bản cũ**. Hai phép kiểm tra này không thay thế nhau. Muốn đánh giá chính xác, phải xét cả bytecode caller, dữ liệu annotation được lưu trong class file và API reflection/processor đang đọc.

## 3. Các kiểu phần tử và quy tắc giá trị hợp lệ

Trước khi thiết kế quá trình chuyển đổi, cần nhớ annotation elements không phải Java method tùy ý. Kiểu trả về hợp lệ của một phần tử thuộc các nhóm:

- Kiểu nguyên thủy, ví dụ `int`, `boolean`.
- `String`.
- `Class` hoặc dạng tham số hóa `Class<?>` thích hợp.
- Một kiểu `enum`.
- Một annotation interface khác.
- **Mảng một chiều** của các kiểu kể trên.

Các kiểu như `Object`, `List<String>`, `LocalDate` hoặc mảng nhiều chiều không phải annotation element type hợp lệ.

Giá trị dùng ở nơi đặt annotation cũng bị giới hạn:

- Với primitive hoặc `String`: **compile-time constant expression** phù hợp.
- Với `Class<?>`: class literal như `String.class`.
- Với enum: enum constant như `Mode.STRICT`.
- Với annotation lồng nhau: `@Nested(...)`.
- Với mảng: `{"a", "b"}` hoặc cú pháp phần tử đơn khi được cho phép.
- **`null` không hợp lệ**, kể cả khi kiểu phần tử là reference type.

Vì vậy, không thể “sửa lỗi migration” bằng cách viết `default null` hoặc `default System.getenv("...")`. Nếu cần sentinel, hãy định nghĩa ý nghĩa của `""`, `{}`, `Void.class` hoặc `UNSPECIFIED` một cách rõ ràng.

## 4. Thêm phần tử mới: có `default` và không có `default`

Giả sử v1:

~~~java
public @interface Rule {
    String name();
    int retries() default 2;
}
~~~

### 4.1. Thêm phần tử có default — lựa chọn dễ tương thích nhất

Ở v2:

~~~java
public @interface Rule {
    String name();
    int retries() default 2;
    int timeoutSeconds() default 30;
}
~~~

Mã cũ sau vẫn biên dịch khi dùng v2:

~~~java
@Rule(name = "payment")
class PaymentService {}
~~~

- `name` tiếp tục được cung cấp tường minh.
- `retries` lấy default `2`.
- `timeoutSeconds` lấy default mới `30`.
- Class file của `PaymentService` được biên dịch theo v1 không có cặp dữ liệu `timeoutSeconds=...`, nhưng khi reflection đọc annotation theo định nghĩa v2, `timeoutSeconds()` có thể trả default `30` mà không cần biên dịch lại class cũ.

**Đây là phương án giảm rủi ro về cú pháp và thiếu dữ liệu**, nhưng chưa chắc giữ nguyên hành vi. Nếu consumer bắt đầu áp dụng timeout `30` mà trước đây hoàn toàn không timeout, hệ thống vẫn có thể thay đổi đáng kể.

Nên chọn default theo **ngữ nghĩa kế thừa hành vi cũ**. Nếu trước đây không có giới hạn timeout, có thể cần sentinel biểu thị “không áp dụng” thay vì tự chọn một timeout có thể phá vỡ tác vụ dài.

### 4.2. Thêm phần tử không có default — breaking change đối với nơi sử dụng

Ở v2:

~~~java
public @interface Rule {
    String name();
    int retries() default 2;
    int timeoutSeconds();
}
~~~

Source cũ:

~~~java
@Rule(name = "payment")
class PaymentService {}
~~~

Khi **biên dịch lại** với v2, compiler yêu cầu giá trị cho `timeoutSeconds`. Code phải đổi, ví dụ:

~~~java
@Rule(name = "payment", timeoutSeconds = 30)
class PaymentService {}
~~~

**Với class file đã biên dịch theo v1**, annotation cũ không chứa `timeoutSeconds`. Nếu runtime reflection truy cập `rule.timeoutSeconds()` trên một annotation instance của class cũ, Java có thể ném **`java.lang.annotation.IncompleteAnnotationException`**. Lỗi có thể xuất hiện khi **đọc phần tử thiếu**, không nhất thiết ngay lúc load class hay khi `getAnnotation(...)` trả về proxy.

**Không nên coi việc thêm một method bắt buộc là một migration tương thích.** Nếu cần buộc các client mới nhập giá trị, hãy cân nhắc thêm phần tử có default/sentinel trong giai đoạn chuyển tiếp, hướng dẫn chuyển đổi và kiểm soát hợp đồng theo phiên bản.

## 5. Đổi `default`: không cần biên dịch lại class cũ vẫn có thể đổi hành vi

Đây là điểm cực kỳ quan trọng của JLS `9.6.2: **default values không được biên dịch thành giá trị tường minh trong từng annotation usage**; chúng được áp dụng **động tại thời điểm annotation được đọc**.

V1:

~~~java
public @interface Rule {
    int retries() default 2;
}
~~~

Class sử dụng không chỉ định element:

~~~java
@Rule
class Job {}
~~~

V2:

~~~java
public @interface Rule {
    int retries() default 5;
}
~~~

Nếu chỉ thay annotation type v1 bằng v2, còn giữ nguyên **`Job.class`** được biên dịch theo v1, phép gọi:

~~~java
Rule rule = Job.class.getAnnotation(Rule.class);
System.out.println(rule.retries());
~~~

có thể in **`5`**, không phải `2`. Class file `Job.class` chưa từng lưu một giá trị tường minh cho `retries`, nên giá trị được lấy từ default hiện tại của annotation interface đang được load.

Ngược lại:

~~~java
@Rule(retries = 2)
class ExplicitJob {}
~~~

Nếu `ExplicitJob.class` đã ghi giá trị `retries=2`, sau khi nâng annotation interface lên v2, nó **tiếp tục đọc `2`** cho phần tử ấy. **Default chỉ ảnh hưởng khi annotation usage không có giá trị tường minh**.

### 5.1. Vì sao đây có thể là breaking change về hành vi?

Giả sử annotation điều khiển:

- Số lần retry khi gọi API.
- Validation được bật/tắt.
- Transaction mode, cache mode, timeout.
- Quyền truy cập, độ rộng logging hoặc serialization policy.

Đổi mặc định có thể ảnh hưởng tới hàng nghìn class không ghi rõ phần tử đó, kể cả khi không có một source diff nào ở những class ấy. Hệ thống vẫn compile/link bình thường nên regression có thể bị bỏ sót nếu chỉ chạy compiler tests.

**Nguyên tắc:** coi thay đổi default mang ý nghĩa runtime hoặc build-time policy là một **thay đổi hợp đồng ngữ nghĩa**, dù method signature không đổi.

### 5.2. Processor và default

Với annotation processing, `AnnotationMirror.getElementValues()` chỉ chứa các phần tử được cung cấp **tường minh** ở nơi sử dụng. `Elements.getElementValuesWithDefaults(mirror)` trả map có thêm giá trị mặc định theo định nghĩa annotation type hiện tại.

Khi nâng phiên bản annotation type, processor cũng có thể đọc giá trị default mới và tạo source khác. Vì vậy, tác động của đổi default **không giới hạn ở reflection runtime**; nó còn có thể làm thay đổi **generated code tại build time**.

## 6. Đổi kiểu phần tử: vì sao không phải phép refactor vô hại?

V1:

~~~java
@interface Policy {
    String mode() default "safe";
}

@Policy(mode = "strict")
class Service {}
~~~

Sau một phiên bản, API muốn dùng enum:

~~~java
enum Mode { SAFE, STRICT }

@interface Policy {
    Mode mode() default Mode.SAFE;
}
~~~

Thay đổi này có các tác động:

1. **Source:** `@Policy(mode = "strict")` **không biên dịch lại**; phải đổi thành `@Policy(mode = Mode.STRICT)`.
2. **Bytecode callers:** method `mode()` của annotation interface đổi return descriptor từ `()Ljava/lang/String;` sang `()L.../Mode;`. Caller đã biên dịch theo signature cũ có thể gặp **`NoSuchMethodError`** khi chạy cùng API mới.
3. **Metadata cũ:** một class file từ v1 có thể chứa element-value `mode="strict"` theo dạng `String`, không tương thích với element type enum của v2. Khi Java reflection đọc element đó theo definition mới, có thể ném **`AnnotationTypeMismatchException`**.
4. **Hành vi:** ngay cả khi bạn sửa source mới, consumer phải xử lý enum thay cho String. Mapping và default cũng có thể đổi.

Không nên mặc định rằng compiler/JVM sẽ tự chuyển chuỗi `"strict"` thành `Mode.STRICT` khi đọc annotation cũ. Metadata trong class file có các dạng giá trị khác nhau; không có hệ thống chuyển đổi type tùy ý theo ý định nghiệp vụ.

### 6.1. Không chỉ `String -> enum`

Các thay đổi cũng rủi ro:

| Kiểu cũ | Kiểu mới | Vấn đề |
|---|---|---|
| `int count()` | `long count()` | Method descriptor thay đổi; caller cũ và element values có thể không tương thích |
| `String tag()` | `String[] tags()` | Thay tên và dạng dữ liệu; code cũ phải migrate, annotation cũ không tự biến scalar thành array |
| `Class<?> handler()` | `String handler()` | Type và contract khác; không tự stringify class literal |
| `Mode mode()` | `NewMode mode()` | Khác enum type; mapping enum constant phải thiết kế |
| `boolean enabled()` | `String enabled()` | Thay type, ảnh hưởng annotation usage và reader |
| `String[] names()` | `String name()` | Không tự lấy một phần tử từ dữ liệu mảng cũ |

Các lỗi có thể khác nhau tùy call site và dữ liệu lưu. **Không hứa duy nhất một exception** cho mọi trường hợp đổi kiểu; các ví dụ kiểm chứng phía dưới cố tình tách reader biên dịch với API mới khỏi caller cũ để thấy loại lỗi phản ánh chính dữ liệu annotation cũ.

### 6.2. Đổi enum và class literal cũng có rủi ro riêng

Nếu annotation cũ có một **enum constant** hoặc **class literal** không còn phân giải được theo môi trường mới, đọc annotation có thể gặp `EnumConstantNotPresentException` hoặc `TypeNotPresentException` khi truy cập phần tử liên quan.

Đây là lỗi ở **thành phần giá trị annotation** đang được đọc, không đơn thuần là thay đổi source syntax. Đổi tên enum constant, di chuyển class hoặc thay gói dependency có thể gây tác động ngay cả khi return type của annotation element không đổi.

## 7. Ví dụ thực nghiệm tương thích: giữ class file cũ khi thay API

Ví dụ này sử dụng **cùng một class `demo.Legacy` đã biên dịch theo v1**, sau đó chạy ba phiên bản annotation interface để kiểm tra hậu quả. Không biên dịch lại `Legacy.java` ở các lượt v2/v3/v4.

### 7.1. Phiên bản v1 — khai báo và sử dụng

File `v1/src/api/Rule.java`:

~~~java
package api;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Rule {
    String name();
    int retries() default 2;
    String mode() default "safe";
}
~~~

File `v1/src/demo/Legacy.java`:

~~~java
package demo;

@api.Rule(name = "alpha", mode = "strict")
public class Legacy {}
~~~

Chú ý: `Legacy` cung cấp `name`, `mode` tường minh nhưng **không cung cấp `retries`**.

Biên dịch v1:

~~~bash
mkdir -p v1/classes
javac --release 17 -d v1/classes \
  v1/src/api/Rule.java v1/src/demo/Legacy.java
~~~

Kết quả: `v1/classes/api/Rule.class` và `v1/classes/demo/Legacy.class`.

### 7.2. Phiên bản v2 — thêm phần tử có default và đổi default cũ

File `v2/src/api/Rule.java`:

~~~java
package api;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Rule {
    String name();
    int retries() default 5;         // v1 là 2
    String mode() default "safe";
    String owner() default "team";   // phần tử mới có default
}
~~~

File `v2/src/demo/Read.java`:

~~~java
package demo;

public class Read {
    public static void main(String[] args) {
        api.Rule rule = Legacy.class.getAnnotation(api.Rule.class);

        System.out.println("name=" + rule.name());
        System.out.println("retries=" + rule.retries());
        System.out.println("mode=" + rule.mode());
        System.out.println("owner=" + rule.owner());
    }
}
~~~

Biên dịch **chỉ Rule v2**, sao chép `Legacy.class` **cũ**, rồi biên dịch reader mới:

~~~bash
mkdir -p v2/classes/demo
javac --release 17 -d v2/classes v2/src/api/Rule.java
cp v1/classes/demo/Legacy.class v2/classes/demo/
javac --release 17 -cp v2/classes -d v2/classes v2/src/demo/Read.java
java -cp v2/classes demo.Read
~~~

Stdout thực tế:

~~~text
name=alpha
retries=5
mode=strict
owner=team
~~~

Giải thích:

- `name=alpha` vẫn là element value tường minh từ annotation cũ.
- `retries=5` lấy **default của v2** dù `Legacy.class` vẫn là binary v1.
- `mode=strict` tiếp tục là **giá trị tường minh** trong class cũ, không bị thay bởi default `"safe"`.
- `owner=team` là element mới nhưng có default nên class cũ vẫn đọc được.

Đây là minh chứng quan trọng nhất cho sự khác nhau giữa **dữ liệu được lưu tường minh trong annotation usage** và **default lấy từ annotation interface được load ở runtime**.

### 7.3. Phiên bản v3 — thêm phần tử bắt buộc không có default

File `v3/src/api/Rule.java` có các phần tử v2 và thêm:

~~~java
int timeout(); // KHÔNG có default
~~~

Đặt dòng trên **bên trong annotation interface Rule**. Bản thân dòng này chưa phải tệp độc lập.

Reader mới tại `v3/src/demo/Read.java` (biên dịch với Rule v3):

~~~java
package demo;

public class Read {
    public static void main(String[] args) {
        api.Rule rule = Legacy.class.getAnnotation(api.Rule.class);
        try {
            System.out.println(rule.timeout());
        } catch (java.lang.annotation.IncompleteAnnotationException ex) {
            System.out.println("missing=" + ex.elementName());
        }
    }
}
~~~

Giữ `Legacy.class` cũ của v1 (nó không có `timeout`). Khi reader gọi `timeout()`, kết quả đã kiểm chứng là:

~~~text
missing=timeout
~~~

`IncompleteAnnotationException` chỉ ra code đang truy cập một element được thêm sau khi annotation usage đã được biên dịch nhưng thiếu giá trị và thiếu default trong definition hiện tại.

Để tái hiện phiên bản này, tạo đầy đủ `Rule.java` của v3 từ v2 bằng cách thêm `int timeout();`, rồi dùng cùng mẫu lệnh của v2 với `v3/classes`. Đừng biên dịch lại `Legacy.java` cùng v3 khi muốn kiểm tra binary cũ: source cũ sẽ bị compiler báo thiếu `timeout`.

### 7.4. Phiên bản v4 — thay kiểu của giá trị đã lưu

File `v4/src/api/Rule.java`:

~~~java
package api;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Rule {
    String name();
    int retries() default 5;
    int mode() default 9; // trước đây String mode()
}
~~~

Reader mới `v4/src/demo/Read.java`:

~~~java
package demo;

public class Read {
    public static void main(String[] args) {
        api.Rule rule = Legacy.class.getAnnotation(api.Rule.class);
        try {
            System.out.println(rule.mode());
        } catch (java.lang.annotation.AnnotationTypeMismatchException ex) {
            System.out.println("mismatch=" + ex.element().getName());
        }
    }
}
~~~

Sử dụng `Legacy.class` từ v1 với `mode="strict"` lưu kiểu `String`, nhưng annotation interface v4 yêu cầu `int`. Kết quả đã kiểm chứng:

~~~text
mismatch=mode
~~~

**Chú ý:** Đây là **reader mới biên dịch với v4**. Nếu thay vào đó giữ một reader binary cũ đã biên dịch để gọi `String mode()` từ API v1, đổi return type của `mode()` có thể gây lỗi **liên kết method** như `NoSuchMethodError`. Cần test cả hai kịch bản nếu phát hành thư viện cho client precompiled.

### 7.5. Ma trận kết quả thực nghiệm

| Cấu hình | `Legacy.class` | `Rule.class` | Reader | Quan sát |
|---|---|---|---|---|
| V2: thêm `owner` có default, đổi default `retries` | V1 | V2 | Biên dịch mới với V2 | `name=alpha`, `retries=5`, `mode=strict`, `owner=team` |
| V3: thêm `timeout` bắt buộc | V1 | V3 | Biên dịch mới với V3 | `IncompleteAnnotationException` khi gọi `timeout()` |
| V4: đổi `mode` từ `String` sang `int` | V1 | V4 | Biên dịch mới với V4 | `AnnotationTypeMismatchException` khi gọi `mode()` |

Bốn phiên bản là **những snapshot thử nghiệm độc lập**, không phải các class `api.Rule` khác nhau đồng thời ở một classpath. Mỗi lần chạy chỉ có **một** định nghĩa `api.Rule` phù hợp với kịch bản. Việc trộn nhiều JAR chứa cùng binary name có thể làm classpath/classloader chọn phiên bản không mong muốn và khiến kết quả nhiễu.

## 8. Thay đổi tên hoặc xóa phần tử

V1:

~~~java
@interface Config {
    String value();
}
~~~

Nếu V2 thay bằng:

~~~java
@interface Config {
    String path();
}
~~~

đây không chỉ là đổi tên biến cục bộ: với annotation element, **tên method là tên element trong metadata**, và bytecode caller có thể phụ thuộc vào chữ ký method.

Tác động:

- Source cũ `@Config("abc")` hoặc `@Config(value="abc")` không tự ánh xạ sang `path`; phải thay cú pháp sử dụng.
- Nếu `path()` không có default, nơi dùng cũ thiếu giá trị bắt buộc.
- Reader cũ gọi `value()` có thể thất bại khi binary mới không còn method đó.
- Annotation usage cũ lưu phần tử tên `value`; việc đổi sang tên `path` không có cơ chế tự rename trong class-file metadata.
- Nếu tên mới có default, hệ thống có thể đọc default nhưng **không có phép chuyển tự động từ giá trị cũ sang giá trị mới**.

Tương tự, **xóa một phần tử** phá vỡ source uses và callers cũ phụ thuộc phần tử bị xóa. Những cặp metadata cũ không được định nghĩa bởi annotation interface mới cũng không thay thế cho method đã bị xóa. Không lấy việc một đoạn reflection “vẫn đọc được annotation” để kết luận xóa element là tương thích.

**Lời khuyên:** Nếu muốn đổi tên một phần tử được dùng rộng rãi, hãy cân nhắc giữ tên cũ trong giai đoạn chuyển tiếp, thêm tên mới có default và cập nhật consumer để đọc theo chính sách ưu tiên minh bạch.

## 9. Chiến lược chuyển đổi an toàn khi cần thay kiểu

Nếu API từ:

~~~java
@interface Settings {
    String mode() default "safe";
}
~~~

sang enum mới, đừng đổi trực tiếp `String mode()` thành `Mode mode()` trong một minor upgrade. Một chiến lược hai bước:

~~~java
enum Mode {
    UNSPECIFIED, SAFE, STRICT
}

@interface Settings {
    @Deprecated
    String mode() default "";  // phần tử cũ, vẫn giữ chữ ký
    Mode modeV2() default Mode.UNSPECIFIED; // phần tử mới
}
~~~

Tại nơi dùng mới:

~~~java
@Settings(modeV2 = Mode.STRICT)
class NewClient {}
~~~

**Vì sao chọn sentinel `UNSPECIFIED`?** Để consumer phân biệt “client mới chọn giá trị enum” với “chưa cung cấp enum, cần xét phần tử legacy hoặc mặc định cũ”. Tuy nhiên, đây chỉ là **quy ước API**: chính annotation không tự thực hiện ưu tiên và không tự chuyển chuỗi thành enum.

Consumer có thể áp dụng chính sách:

1. Nếu `modeV2() != UNSPECIFIED`, dùng enum mới.
2. Ngược lại, nếu `mode()` không rỗng, ánh xạ giá trị legacy `"safe"/"strict"` một cách tường minh sang enum.
3. Nếu cả hai không được chỉ định, dùng **chính sách fallback được tài liệu hóa**.
4. Nếu cả hai được chỉ định nhưng mâu thuẫn, báo lỗi rõ ràng thay vì chọn ngẫu nhiên.

Snippet minh họa logic đọc:

~~~java
static Mode resolve(Settings settings) {
    if (settings.modeV2() != Mode.UNSPECIFIED) {
        return settings.modeV2();
    }
    return switch (settings.mode()) {
        case "", "safe" -> Mode.SAFE;
        case "strict" -> Mode.STRICT;
        default -> throw new IllegalArgumentException(
                "Unknown legacy mode: " + settings.mode());
    };
}
~~~

Code trên là **helper minh họa**, cần đặt trong class có thể thấy `Settings`, `Mode`. Nó xử lý source mới và cũ có phần tử legacy, nhưng không thể tự khôi phục những metadata đã bị xóa khỏi binary hoặc xử lý mọi lỗi do đổi ABI tùy ý.

Khi triển khai migration:

- Ra phiên bản **A** thêm `modeV2() default UNSPECIFIED`, vẫn giữ `mode()`.
- Cập nhật processor/framework để hiểu cả hai và cảnh báo việc dùng giá trị cũ.
- Chuyển dần các annotation usages sang `modeV2`; test các class/JAR chưa được biên dịch lại.
- Chỉ cân nhắc **xóa legacy element** ở phiên bản phá vỡ hợp đồng có chủ đích, sau khi client được cập nhật.
- Nếu consumer có chính sách bảo mật/validation, không tự ý chuyển từ chế độ an toàn sang mặc định dễ dãi.

## 10. Thay đổi `@Target`, `@Retention`, `@Inherited` và `@Repeatable` cũng là tiến hóa hợp đồng

Mặc dù đề bài trọng tâm là element/default/type, một annotation interface còn nhiều phần của hợp đồng có thể gây breaking changes.

### 10.1. Thay `@Target`

Nếu ban đầu:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Marker {}
~~~

rồi v2 chỉ cho phép `METHOD`, những source đang đặt `@Marker` trên class không còn biên dịch. **Thu hẹp target** thường là breaking source change. Mở rộng target có thể giúp người dùng mới nhưng cần bảo đảm consumer biết cách xử lý metadata ở các vị trí mới.

### 10.2. Thay `@Retention`

Đổi `RUNTIME` thành `CLASS` làm Java reflection không còn nhìn thấy annotation theo cách trước, ngay cả khi metadata vẫn nằm trong class file ở nhóm `RuntimeInvisible...`. Đổi `SOURCE` thành `RUNTIME` cho các lần biên dịch mới không làm các class file cũ vốn không lưu annotation `SOURCE` tự nhiên xuất hiện metadata runtime; cần biên dịch lại những usages cần giữ annotation.

### 10.3. Thay `@Inherited`

Đổi cấu hình `@Inherited` có thể thay đổi kết quả `Class.getAnnotation(...)` trên subclasses khi annotation type được đọc. Nhưng `@Inherited` chỉ áp dụng theo superclass cho annotation trên class, không tự áp dụng lên override methods hay các interfaces đã `implements`.

### 10.4. Thay `@Repeatable` và container

Khi cho phép annotation type lặp, cần xác định container phù hợp: có element `value()` kiểu mảng của annotation gốc, những method khác có default phù hợp, retention/target theo quy tắc ngôn ngữ. Code đang dùng `getAnnotation(Foo.class)` có thể không thấy các annotation lặp được biểu diễn qua container, trong khi `getAnnotationsByType(Foo.class)` xử lý loại này.

Thay container, retention hay target của repeatable annotation có thể ảnh hưởng source compilation, class-file representation và reader framework. **Không nên biến một annotation singleton API thành repeatable chỉ bằng cách nhìn cú pháp `@Repeatable` mà bỏ qua compatibility tests**.

## 11. Annotation defaults trong class file và `javap -v`

Khi biên dịch annotation interface:

~~~java
@interface Limit {
    int retries() default 2;
}
~~~

Compiler lưu **default của phần tử** trong attribute `AnnotationDefault` gắn với method `retries()` ở file class của **annotation interface**.

Còn với:

~~~java
@Limit
class Service {}
~~~

Annotation usage trên `Service` không cần lưu một element-value pair `retries=2`. Nếu đổi default trong `Limit.class` sang `5`, phần tử được đọc từ `Service.class` cũ sẽ lấy `5` theo definition mới.

Để tự đối chiếu khi có JDK:

~~~bash
javac --release 17 Limit.java Service.java
javap -v -p Limit
javap -v -p Service
~~~

- Trong `Limit.class`, tìm `AnnotationDefault` ở element method.
- Trong `Service.class`, tìm `RuntimeVisibleAnnotations` nếu `Limit` có retention `RUNTIME`; nếu không khai báo `@Retention`, mặc định là `CLASS`, nên tìm `RuntimeInvisibleAnnotations`.
- Với `@Limit(retries=2)` tường minh, `Service.class` chứa giá trị tương ứng trong annotation usage.

**Không đọc nhầm** các constant-pool references hoặc giá trị default trong annotation interface thành một giá trị tường minh trong từng client annotation.

## 12. Hệ quả đối với annotation processors, code generators và framework

Có hai kiểu consumer phổ biến:

**(A) Annotation processor ở compile-time**

~~~java
AnnotationMirror mirror = /* metadata từ Element */;
var explicit = mirror.getElementValues();
var effective = processingEnv.getElementUtils()
        .getElementValuesWithDefaults(mirror);
~~~

- `explicit` chỉ có các phần tử khai báo tường minh tại nơi sử dụng.
- `effective` có thêm defaults theo định nghĩa annotation type hiện tại.
- Thêm element/default hoặc đổi default có thể thay đổi file generated ngay khi build lại.
- Đổi kiểu/names còn làm các processor đang tìm element bằng tên, type hoặc annotation proxy thất bại nếu không migrate.
- Processor cần báo diagnostic rõ ràng nếu annotation được sử dụng không hợp lệ hoặc giá trị legacy xung đột.

**(B) Runtime framework dùng reflection**

~~~java
Rule rule = serviceClass.getAnnotation(Rule.class);
int retries = rule.retries();
~~~

- Đổi default có thể tác động đến class file chưa biên dịch lại.
- Thêm required element không có default có thể gây `IncompleteAnnotationException` khi được truy cập.
- Kiểu dữ liệu lưu không còn phù hợp có thể gây `AnnotationTypeMismatchException`.
- Đổi enum constant/class literal có thể gặp các lỗi phân giải type tương ứng.
- Đổi retention/target/inheritance thay đổi sự hiện diện của metadata.

Đừng chỉ test annotation interface “biên dịch được”; hãy test **client precompiled + annotation type mới + reader mới/cũ**. Với framework cache metadata, còn cần xem lifecycle của cache và class loader để tránh so sánh kết quả từ hai phiên bản không tương ứng.

## 13. Chiến lược versioning và kiểm thử hồi quy

### 13.1. Bảng quyết định trước khi phát hành

| Thay đổi | Tương thích source cũ | Rủi ro runtime/behavior | Chiến lược |
|---|---|---|---|
| Thêm element **có default** | Thường giữ được | Default mới có thể đổi semantics | Chọn default bảo tồn hành vi cũ, test binaries |
| Thêm element **không default** | **Không** ở usages cũ | `IncompleteAnnotationException` khi đọc annotation cũ | Breaking release hoặc migration có default |
| Đổi giá trị default | Thường giữ được | **Cao nếu điều khiển policy**; ảnh hưởng class cũ | Version contract, kiểm kê implicit usages |
| Đổi element type | Thường **không** | Mismatch/linkage | Thêm element mới song song, deprecate cũ |
| Đổi tên element | Thường **không** | Client cũ và dữ liệu theo tên cũ | Alias/bridge có giai đoạn chuyển tiếp |
| Xóa element | **Không** nếu source dùng element | Caller cũ có thể không còn method | Major/breaking release theo chính sách dự án |
| Thu hẹp `@Target` | Không cho usages bị loại | Source build fail | Tránh nếu chưa chuyển usages |
| Đổi `RUNTIME -> CLASS` | Cú pháp có thể vẫn hợp lệ | Reflection thiếu metadata | Phát hành breaking và test framework |
| Thay enum constant đang được dùng | Không cho code tham chiếu constant cũ | `EnumConstantNotPresentException` có thể xảy ra | Giữ constant hoặc migration có chủ đích |

Từ “thường” ở bảng nhằm nhắc tới **ngữ cảnh**: một API còn có kiểu lồng nhau, generic bounds, annotation inheritance, processor settings và bytecode caller. Bảng này là định hướng review, không thay JLS hoặc phép thử thực tế.

### 13.2. Bộ test nên có

1. **Recompile source clients cũ** với annotation interface mới để phát hiện incompatibility source.
2. **Giữ nguyên `.class` cũ**, thay annotation interface mới rồi đọc bằng reflection; không vô tình biên dịch lại tất cả.
3. **Chạy reader binary cũ** với API mới nếu thư viện phải hỗ trợ artifact đã phát hành.
4. **Kiểm tra explicit/default phân biệt**: `@Rule(retries=2)` và `@Rule` có hành vi khác nhau khi đổi default.
5. **Kiểm tra các exception cụ thể**: thiếu required element, kiểu mismatch, enum constant/class literal không còn hợp lệ.
6. **Chạy annotation processor** với source phiên bản cũ/mới; so sánh generated files và diagnostics.
7. **Kiểm tra API contract của framework**: target, retention, superclass, interface, repeatable annotation, metadata caching.
8. **Kiểm tra các phiên bản JDK/build thực tế** mà sản phẩm hỗ trợ; đừng chỉ tin vào test một JVM.
9. **Ghi migration guide** và cách chuyển annotation usages, kể cả các module/JAR chưa thể biên dịch lại ngay.

### 13.3. Cần tránh “silent semantic break”

Một thay đổi default từ `false` sang `true` cho một annotation điều khiển chức năng hoặc kiểm tra bảo mật có thể gây ảnh hưởng nghiêm trọng mà không có compiler error. Những thay đổi như vậy cần review tương đương thay đổi cấu hình mặc định của API sản phẩm.

Nên cân nhắc:

- Dùng **tên phần tử mới** để biểu diễn ý nghĩa mới, thay vì tái định nghĩa tùy ý giá trị cũ.
- Nếu có phiên bản chính sách, dùng một element riêng như `policyVersion() default 1` và đọc có điều kiện, nhưng cần kiểm soát rủi ro của bản thân default.
- Thiết kế migration bằng **default/sentinel + warning + loại bỏ có chủ đích**, không đổi type ngay.
- Tài liệu hóa chính xác ý nghĩa giá trị khi không được chỉ định, tránh để consumer tự suy ra từ một chuỗi bất kỳ.

## 14. Những nhầm lẫn hay gặp

### “Thêm một method vào `@interface` không ảnh hưởng code cũ.”

Không đúng nếu method là một **element mới không có default**. Source cũ thiếu giá trị bắt buộc, và annotation trong binary cũ có thể gây `IncompleteAnnotationException` khi đọc.

### “Đổi `default` chỉ ảnh hưởng class được biên dịch lại.”

Sai. JLS quy định default được áp dụng khi annotation được đọc; usages **không ghi tường minh** có thể lấy default mới ngay cả với binary cũ.

### “Một element `String` được đổi thành enum thì string cũ tự chuyển được.”

Không. Annotation element values tuân các kiểu/cách mã hóa đặc thù. Metadata cũ có thể gây mismatch; phải viết migration và kiểm thử.

### “Thêm `@Retention(RUNTIME)` sẽ làm annotation `SOURCE` trong JAR cũ xuất hiện.”

Không. Nếu annotation không được lưu tại lúc biên dịch trước đó, đổi retention type sau này không tự dựng lại dữ liệu đã mất.

### “Tôi đã đổi tên element nhưng framework có thể đoán giá trị cũ.”

Framework không có quy tắc Java mặc định để ánh xạ mọi element theo tên cũ sang tên mới. Muốn hỗ trợ, phải giữ bridge/sentinel hoặc tự triển khai migration theo nguồn và dữ liệu lưu.

### “`@Deprecated` làm method cũ biến mất khỏi API.”

`@Deprecated` đánh dấu cảnh báo/ý định không khuyến khích dùng, nhưng method vẫn tồn tại cho đến khi bị xóa. Đây là lý do có thể giữ element legacy qua một giai đoạn chuyển tiếp.

### “Nếu `getAnnotation` trả khác `null` thì mọi element đều đọc an toàn.”

Không. Một annotation proxy có thể tồn tại nhưng truy cập **một element cụ thể** mới dẫn tới `IncompleteAnnotationException`, mismatch hoặc lỗi phân giải enum/class.

### “Source compatibility và behavioral compatibility là một.”

Không. Đổi default thường là trường hợp phản ví dụ: source vẫn hợp lệ, method signature có thể giữ nguyên, nhưng policy khi chạy đã khác.

## 15. Checklist cho người thiết kế annotation API

- [ ] Liệt kê toàn bộ element names, types, defaults, `@Target` và `@Retention` của phiên bản hiện tại.
- [ ] Phân biệt usages cung cấp giá trị tường minh và usages phụ thuộc default.
- [ ] Nếu thêm element: có thể đưa một default phù hợp ngữ nghĩa cũ không?
- [ ] Nếu buộc client cung cấp một giá trị mới: đã coi đó là breaking source change chưa?
- [ ] Nếu đổi type/name: có kế hoạch giữ element cũ và thêm element mới thay vì sửa trực tiếp chữ ký không?
- [ ] Nếu đổi default: đã kiểm chứng hành vi của **class file chưa biên dịch lại** chưa?
- [ ] Nếu thay enum/class literal: đã kiểm tra các giá trị từng được lưu trong artifact cũ chưa?
- [ ] Nếu consumer dùng reflection: đã thử các exception khi truy cập element cụ thể chưa?
- [ ] Nếu consumer là processor: đã phân biệt `getElementValues()` với `getElementValuesWithDefaults()` chưa?
- [ ] Nếu API có repeatable/inherited annotation: đã test container/retention/target chưa?
- [ ] Có migration guide, compatibility tests trên JDK mục tiêu và versioning policy rõ ràng chưa?

## 16. Tài liệu chuẩn để đối chiếu

- [JLS Java SE 17 `9.6.1 — Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1): kiểu phần tử và quy tắc khai báo element.
- [JLS Java SE 17 `9.6.2 — Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2): default được áp dụng khi annotation được đọc; thay default tác động tới usages không chỉ định tường minh.
- [JLS Java SE 17 `9.7.1 — Normal Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1): các giá trị annotation hợp lệ và quy tắc commensurability.
- [JLS Java SE 17 Chương 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): các quy tắc binary compatibility khi API Java tiến hóa.
- [Java SE 17 — `IncompleteAnnotationException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/IncompleteAnnotationException.html): truy cập element mới thiếu giá trị và default của annotation cũ.
- [Java SE 17 — `AnnotationTypeMismatchException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/AnnotationTypeMismatchException.html): giá trị annotation trong binary không tương thích với element type hiện tại.
- [Java SE 17 — `AnnotationMirror`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html) và [`Elements.getElementValuesWithDefaults`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): phân biệt giá trị tường minh và default trong annotation processing.
- [Java SE 17 JVM Spec `4.7.22 — `AnnotationDefault`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.22): biểu diễn default ở class file của annotation interface.

**Kết luận:** Trong một thư viện Java đã có client sử dụng, **thêm phần tử với default** thường là phương án ít gây lỗi nhất; **thêm phần tử bắt buộc** hoặc **đổi tên/kiểu** có thể phá vỡ client source và metadata binary; **đổi default** đặc biệt nguy hiểm vì có thể đổi hành vi ngay với annotation usages cũ chưa biên dịch lại. Hãy quản lý annotation như một hợp đồng API thật sự, kiểm tra source, binary, reflection, processor và ngữ nghĩa trước khi phát hành.