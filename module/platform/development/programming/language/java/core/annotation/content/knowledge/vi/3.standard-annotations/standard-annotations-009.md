# Phân biệt annotation của Java SE và annotation từ thư viện ngoài

## 1. Vì sao cần phân biệt?

Trong Java, các annotation đều sử dụng cú pháp `@TenAnnotation`, nhưng **chúng không cùng nguồn gốc và không có cùng cơ chế hoạt động**. Một annotation có thể được định nghĩa trong Java SE, trong một thư viện/framework bên thứ ba hoặc ngay trong mã nguồn dự án.

Khi đọc:

```java
@Override
@Deprecated
public String toString() {
    return "example";
}
```

ta đang gặp hai annotation chuẩn của Java SE. Nhưng khi đọc:

```java
@org.junit.jupiter.api.Test
void shouldCalculateTotal() {
    // Một phương thức kiểm thử do JUnit quản lý
}
```

ta đang gặp annotation thuộc **JUnit Jupiter**, phải có thư viện tương ứng trong dự án và phải chạy bằng công cụ kiểm thử phù hợp.

Việc **Java hỗ trợ cú pháp annotation** không có nghĩa Java tự biết phải làm gì với mọi annotation. Phần lớn annotation chỉ cung cấp metadata; hành vi cụ thể xuất hiện khi trình biên dịch, công cụ hoặc một chương trình/framework đọc và xử lý metadata đó.

Phân biệt theo ba câu hỏi:

1. **Ai định nghĩa annotation?** Java SE, thư viện ngoài hay chính dự án?
2. **Có cần thêm dependency?** JDK đã cung cấp kiểu annotation chưa, hay phải tải artifact tương ứng?
3. **Ai xử lý, vào lúc nào?** Java compiler, annotation processor, test runner, framework runtime hay code reflection của ứng dụng?

Không được chỉ nhìn tiền tố `@` hoặc việc annotation xuất hiện ở runtime rồi kết luận đó là annotation chuẩn Java.

## 2. Annotation thuộc Java SE là gì?

**Java SE (Java Platform, Standard Edition)** cung cấp sẵn một tập annotation và meta-annotation trong các API chuẩn. Các kiểu thường gặp nằm trong `java.lang` và `java.lang.annotation`; một số API chuẩn khác cũng định nghĩa annotation riêng.

Ví dụ cơ bản có thể dùng trực tiếp trong ứng dụng Java 17+ mà **không cần khai báo dependency bên thứ ba**:

| Annotation | Tên đầy đủ/package | Mục đích chính | Thành phần liên quan |
| --- | --- | --- | --- |
| `@Override` | `java.lang.Override` | Yêu cầu kiểm tra phương thức có thực sự override/implement một phương thức hợp lệ | Trình biên dịch Java |
| `@Deprecated` | `java.lang.Deprecated` | Đánh dấu API không còn được khuyến khích sử dụng | Compiler, IDE, tài liệu và các công cụ đọc metadata |
| `@SuppressWarnings` | `java.lang.SuppressWarnings` | Yêu cầu compiler bỏ qua các nhóm cảnh báo được nhận diện | Trình biên dịch Java |
| `@FunctionalInterface` | `java.lang.FunctionalInterface` | Kiểm tra interface thỏa hợp đồng functional interface | Trình biên dịch Java |
| `@SafeVarargs` | `java.lang.SafeVarargs` | Khẳng định an toàn ở các khai báo dùng generic/varargs hợp lệ để giảm cảnh báo liên quan | Trình biên dịch Java |
| `@Target` | `java.lang.annotation.Target` | Khai báo vị trí mà một annotation được phép xuất hiện | Trình biên dịch; định nghĩa annotation |
| `@Retention` | `java.lang.annotation.Retention` | Khai báo chính sách giữ metadata: SOURCE, CLASS, RUNTIME | Compiler, class file, reflection |
| `@Documented` | `java.lang.annotation.Documented` | Đánh dấu annotation nên xuất hiện trong tài liệu API do công cụ hỗ trợ sinh ra | Công cụ tài liệu, ví dụ Javadoc |
| `@Inherited` | `java.lang.annotation.Inherited` | Cho phép tra cứu annotation ở superclass theo quy tắc kế thừa cụ thể đối với class declaration | Reflection Java |
| `@Repeatable` | `java.lang.annotation.Repeatable` | Cho phép áp dụng nhiều lần một loại annotation theo quy tắc container | Trình biên dịch và các API đọc annotation |

Các annotation trong `java.lang` được import ngầm; đối với các meta-annotation thuộc `java.lang.annotation`, thường phải `import` rõ ràng.

**Lưu ý:** “Được Java SE cung cấp” nói về **nguồn gốc API**, không khẳng định annotation sẽ tự kích hoạt logic nghiệp vụ. Ví dụ, `@Deprecated` có tác động đến công cụ và cảnh báo nhưng không tự ngăn người dùng gọi phương thức.

### 2.1. Những annotation Java SE được trình biên dịch hiểu trực tiếp

```java
class Base {
    String label() {
        return "base";
    }
}

class Child extends Base {
    @Override
    @Deprecated(since = "17")
    String label() {
        return "child";
    }
}
```

Trong ví dụ này:

- `@Override` làm compiler báo lỗi nếu `label()` không còn override được một phương thức hợp lệ ở kiểu cha; không có cơ chế gọi phương thức nào được tạo bởi annotation.
- `@Deprecated(since = "17")` biểu thị phiên bản bắt đầu deprecate; đây là thông tin cho compiler/công cụ, không phải lệnh cấm sử dụng.
- Cả hai loại đều chuẩn Java SE và có thể áp dụng trên cùng phương thức nếu hợp lệ với `@Target`.

Một số annotation chuẩn được compiler kiểm tra về vị trí hoặc hợp đồng; `@SafeVarargs`, chẳng hạn, **không hợp lệ trên mọi phương thức**. Cần đọc điều kiện riêng của nó, thay vì cho rằng tất cả annotation chuẩn đều đặt được ở bất cứ đâu.

### 2.2. Meta-annotation cũng là annotation chuẩn

Meta-annotation là **annotation dùng để mô tả một loại annotation khác**. Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface AuditAction {
    String value();
}
```

`@Retention` và `@Target` ở đây được **Java SE** cung cấp. `@AuditAction` là **annotation tự định nghĩa**, dù nó sử dụng hai meta-annotation chuẩn. Không vì thấy `@Target` hoặc `@Retention` mà xem `@AuditAction` là annotation có sẵn trong JDK.

## 3. Annotation từ thư viện ngoài là gì?

Đây là các kiểu annotation được đóng gói và phân phối bởi một thư viện, framework hoặc tổ chức khác với bộ API chuẩn Java SE. Java vẫn chấp nhận chúng vì **thư viện cũng có thể khai báo `@interface`** theo ngôn ngữ Java.

| Hệ sinh thái | Ví dụ annotation và package | Thư viện/thành phần xử lý | Công dụng điển hình |
| --- | --- | --- | --- |
| JUnit Jupiter | `org.junit.jupiter.api.Test` | JUnit Jupiter và nền tảng chạy test | Đánh dấu phương thức test được test engine phát hiện |
| Spring Framework | `org.springframework.stereotype.Component` | Spring container với cơ chế component scanning tương ứng | Đánh dấu kiểu là ứng viên để đăng ký Spring bean |
| Spring Framework | `org.springframework.transaction.annotation.Transactional` | Transaction infrastructure của Spring | Khai báo ngữ nghĩa transaction khi cách gọi và cấu hình được hỗ trợ |
| Jakarta Bean Validation | `jakarta.validation.constraints.NotNull` | Bean Validation provider hoặc tích hợp có gọi validation | Khai báo ràng buộc giá trị không được null |
| Project Lombok | `lombok.Getter` | Công cụ tích hợp với trình biên dịch của Lombok | Sinh getter khi biên dịch theo cấu hình và khả năng hỗ trợ |

**Các ví dụ này không phải API Java SE.** Dự án cần đưa thư viện tương ứng vào dependency/classpath/module path khi biên dịch, và nhiều trường hợp còn cần công cụ hoặc cấu hình runtime phù hợp.

### 3.1. JUnit: test runner thực thi bài kiểm thử

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsNumbers() {
        assertEquals(4, 2 + 2);
    }
}
```

**Đây là đoạn mã dùng JUnit Jupiter, không phải chương trình Java SE tự chạy độc lập.** Cần dependency JUnit Jupiter và bộ chạy test hỗ trợ JUnit Platform (chẳng hạn cấu hình task test của Gradle hoặc công cụ trong IDE).

`@Test` cho JUnit biết phương thức `addsNumbers()` là một bài test; **`java CalculatorTest` không phải lệnh chạy test tương đương với JUnit runner**. Nếu không có JUnit trên classpath, `javac` không thể phân giải các import `org.junit.jupiter.api.*`.

### 3.2. Spring: annotation cần Spring container và infrastructure

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
class AccountService {
    @Transactional
    public void transfer() {
        // Logic nghiệp vụ được viết tại đây
    }
}
```

Đây là mã minh họa yêu cầu Spring dependencies; **không thể biên dịch với JDK thuần**. `@Component` có tác dụng khi Spring quét và đăng ký kiểu vào ApplicationContext phù hợp. `@Transactional` cần transaction management được bật/cấu hình và cơ chế interceptor tương ứng để áp dụng transaction thực tế; phương thức được gọi theo cách không đi qua cơ chế can thiệp có thể không được áp dụng transaction như mong đợi.

Java compiler chỉ xác nhận kiểu annotation tồn tại và việc dùng nó hợp lệ theo các quy tắc ngôn ngữ; compiler Java **không tự tạo Spring bean hoặc tự mở transaction** chỉ vì gặp `@Component` hay `@Transactional`.

### 3.3. Jakarta Validation: constraint cũng cần cơ chế kiểm tra

```java
import jakarta.validation.constraints.NotNull;

class OrderRequest {
    @NotNull
    String customerId;
}
```

`@NotNull` ở đây thuộc API **Jakarta Validation**, không phải Java SE. Ràng buộc được áp dụng khi có Bean Validation provider và ứng dụng/framework thực sự gọi cơ chế validation trên đối tượng; chỉ khởi tạo `new OrderRequest()` rồi để `customerId == null` **không tự phát sinh lỗi**.

Cũng phải phân biệt `jakarta.validation.constraints.NotNull` với các annotation tên gần giống như `org.jetbrains.annotations.NotNull` hay `javax.annotation.Nonnull`: tên gần giống **không đảm bảo cùng nguồn gốc, hợp đồng hoặc công cụ xử lý**.

### 3.4. Lombok: annotation phục vụ khâu biên dịch

```java
import lombok.Getter;

class Customer {
    @Getter
    private String name;
}
```

`@Getter` là của Lombok. Trong môi trường có Lombok được tích hợp và cấu hình đúng, công cụ của Lombok có thể sinh getter lúc biên dịch. Java compiler thuần **không tự biết yêu cầu sinh getter từ `@Getter`**. Cần phân biệt cơ chế Lombok tích hợp vào compiler với những annotation được framework đọc bằng reflection tại runtime.

Đừng gán mọi annotation thư viện ngoài vào một nhóm “chạy ở runtime”: JUnit gắn với test engine, Spring gắn với container/proxy/interceptor, Jakarta Validation gắn với validator, còn Lombok xử lý trong quá trình biên dịch.

## 4. So sánh theo các khía cạnh thực tế

| Tiêu chí | Annotation chuẩn Java SE | Annotation thư viện ngoài |
| --- | --- | --- |
| Nguồn định nghĩa | API chuẩn của Java SE, có trong JDK tương ứng | JAR/module của thư viện hoặc framework |
| Có cần dependency ngoài JDK để tham chiếu không? | Không, nếu API thuộc tập module Java SE khả dụng trong môi trường đang dùng | Thông thường có |
| Cú pháp Java | `@AnnotationName`, có thể khai báo phần tử và giá trị | **Giống hệt** cú pháp Java |
| Kiểm tra cú pháp, `@Target`, kiểu giá trị | Compiler Java | **Vẫn do compiler Java** thực hiện |
| Xử lý ý nghĩa chính | Compiler, công cụ Java SE, thư viện hoặc mã ứng dụng tùy loại | Thư viện, framework, annotation processor, công cụ bên ngoài tùy loại |
| Retention | Mỗi loại tự quy định; không mặc định là RUNTIME | Mỗi loại tự quy định; không mặc định là RUNTIME |
| Reflection | Chỉ đọc được metadata phù hợp với RUNTIME retention | Cũng tuân theo quy tắc Java về retention và reflection |
| Tính di động | Không phụ thuộc thư viện ngoài nhưng vẫn phụ thuộc phiên bản Java hỗ trợ API | Cần tương thích phiên bản thư viện, cấu hình và môi trường triển khai |

Không phải mọi annotation Java SE đều có một “hành vi tự chạy”; cũng không phải mọi annotation bên ngoài đều yêu cầu một framework lớn. Có thể có annotation chỉ là metadata để công cụ riêng đọc.

## 5. Chương trình Java 17+ chạy độc lập: phân biệt Java SE và annotation tự định nghĩa

Ví dụ này cố ý **không dùng thư viện ngoài** để thấy rõ annotation chuẩn Java SE (`@Deprecated`, `@Retention`, `@Target`) và annotation tự định nghĩa (`@Purpose`) có thể tồn tại cạnh nhau.

Tạo file **AnnotationOriginDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Purpose {
    String value();
}

public class AnnotationOriginDemo {
    @Deprecated(since = "17")
    @Purpose("learning")
    public static String hello() {
        return "Hello Java";
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = AnnotationOriginDemo.class.getDeclaredMethod("hello");

        System.out.println(method.isAnnotationPresent(Deprecated.class));
        System.out.println(method.getAnnotation(Purpose.class).value());
        System.out.println(hello());
    }
}
```

Dùng JDK 17 trở lên, ở thư mục chứa file:

```bash
javac AnnotationOriginDemo.java
java AnnotationOriginDemo
```

Kết quả stdout:

```text
true
learning
Hello Java
```

**Giải thích:**

1. `@Deprecated` đến từ `java.lang.Deprecated`, một kiểu chuẩn Java SE. Nó có **RUNTIME retention**, vì thế `isAnnotationPresent(Deprecated.class)` trả về `true`.
2. `@Purpose` do chính file này định nghĩa bằng `@interface`. Nó **không phải annotation chuẩn Java SE và cũng không phải của thư viện ngoài**.
3. `@Retention` và `@Target` đến từ `java.lang.annotation`. Nhờ `@Retention(RUNTIME)`, Java reflection đọc được `@Purpose("learning")` và lấy ra chuỗi `learning`.
4. Hai annotation cùng gắn vào phương thức `hello()`; chỉ có code trong `main()` chủ động đọc chúng. Lời gọi `hello()` bình thường vẫn trả về `Hello Java`.

Có thể dùng đoạn mã này để tách bạch **nguồn gốc của định nghĩa annotation** và **cơ chế đọc annotation**. Reflection thuộc Java SE có thể đọc một annotation tự định nghĩa hoặc bên thứ ba, miễn annotation đó khả dụng cho runtime và được lưu giữ đúng cách.

### 5.1. Vì sao không thấy mọi annotation qua reflection?

`@Override` và `@SuppressWarnings` là annotation chuẩn nhưng có chính sách lưu giữ **SOURCE**, nên reflection tại runtime không thấy chúng. Ngược lại, `@Deprecated` có **RUNTIME**. Một annotation thư viện ngoài cũng có thể là SOURCE, CLASS hoặc RUNTIME.

Vì thế không được dùng tiêu chí “reflection đọc được” để phân loại Java SE hay thư viện ngoài. Retention là **thuộc tính của từng kiểu annotation**, độc lập với bên cung cấp nó.

## 6. Cách xác định nguồn gốc annotation khi đọc một dự án

Khi thấy một annotation lạ, hãy thực hiện theo thứ tự:

1. **Mở định nghĩa hoặc import** để lấy tên đầy đủ (fully qualified class name). Ví dụ `@Test` ở đầu file có thể được import từ JUnit hoặc một thư viện khác; chỉ có tên ngắn `Test` là chưa đủ.
2. **Xem annotation nằm trong JDK hay artifact dependency.** Dùng Go to Declaration trong IDE; xem mục External Libraries, Maven/Gradle dependency graph hoặc tên JAR/module chứa class.
3. **Đọc `@Target` và `@Retention`.** Chúng cho biết vị trí được phép gắn và khả năng xuất hiện của metadata ở runtime, không trực tiếp cho biết ai thực thi nghiệp vụ.
4. **Tìm công cụ tiêu thụ annotation.** Java compiler, annotation processor, JUnit runner, Spring context/proxy, validator hoặc đoạn code reflection của dự án là các cơ chế rất khác nhau.
5. **Kiểm tra dependency và cấu hình kích hoạt.** Biên dịch được vì có annotation type trên classpath **chưa đảm bảo** logic framework tương ứng đang chạy.
6. **Đối chiếu tài liệu của chính annotation và phiên bản thư viện.** Hai thư viện cùng có tên `@Transactional`, `@NotNull` hoặc `@Test` không nhất thiết có hợp đồng và cách vận hành giống nhau.

Ví dụ các import sau cho thấy rõ nguồn gốc:

```java
import java.lang.annotation.Retention;                // Java SE
import org.junit.jupiter.api.Test;                    // JUnit Jupiter
import org.springframework.stereotype.Component;      // Spring
import jakarta.validation.constraints.NotNull;       // Jakarta Validation
```

Đoạn trên **chỉ để minh họa cách đọc package**; muốn biên dịch tất cả các import trong cùng file, phải cung cấp dependency tương ứng cho JUnit, Spring và Jakarta Validation.

### 6.1. Đừng đoán chỉ bằng tiền tố package

- `java.lang.Override` là API Java SE.
- `javax.annotation.processing.Generated` cũng thuộc **API chuẩn đi kèm JDK** (module `java.compiler`), dù package bắt đầu bằng `javax`.
- `jakarta.validation.constraints.NotNull` thuộc Jakarta Validation và **không nằm trong Java SE**.
- Nhiều API từng mang tên `javax.*` trong Java EE hoặc một thư viện ngoài; sự hiện diện của `javax` không đủ để kết luận nó được đóng gói trong JDK hiện tại.
- Một số annotation có tên ngắn trùng nhau nhưng khác package; import quyết định kiểu thực sự được sử dụng.

Vì vậy, **package đầy đủ + nguồn artifact/module + tài liệu phiên bản đang sử dụng** là căn cứ đáng tin cậy hơn tên ngắn.

### 6.2. Dependency có và không có thì khác gì?

Một đoạn dùng annotation ngoài thường có ba trạng thái cần tách biệt:

| Trạng thái | Điều có thể xảy ra |
| --- | --- |
| Thiếu dependency chứa annotation khi biên dịch source | Compiler báo không tìm được package/symbol khi gặp import hoặc sử dụng kiểu đó |
| Có annotation type trên classpath nhưng chưa có bộ xử lý/cấu hình cần thiết | Mã có thể biên dịch, nhưng tác dụng mong muốn của framework/test/tool chưa được kích hoạt |
| Có đúng thư viện, bộ xử lý, cấu hình và luồng thực thi | Annotation có thể được xử lý theo đúng hợp đồng riêng của thư viện |

Trường hợp cụ thể còn tùy kiến trúc: annotation processor cần được kích hoạt trong build; test cần được JUnit runner phát hiện; transaction trong Spring thường gắn với cơ chế proxy/interceptor; validation cần được gọi ở đường thực thi liên quan.

## 7. Phân biệt ba yếu tố thường bị trộn lẫn

### 7.1. Nguồn gốc khác nhau

- **Java SE annotation:** định nghĩa nằm trong API Java SE chuẩn; ví dụ `@Override`.
- **Third-party annotation:** định nghĩa đến từ dependency bên ngoài Java SE; ví dụ `org.junit.jupiter.api.Test`.
- **Custom annotation:** tự định nghĩa trong project; ví dụ `@Purpose` ở mục 5.

Cùng cú pháp `@...`, nhưng cách phân loại thuộc về **nơi định nghĩa kiểu**. Một custom annotation dự án cũng có thể trở thành third-party annotation đối với dự án khác khi được phát hành thành thư viện.

### 7.2. Nơi định nghĩa khác nơi xử lý

Ví dụ `@Test` do JUnit định nghĩa và JUnit xử lý; `@Deprecated` do Java SE định nghĩa và compiler/IDE có thể đọc; `@Purpose` do dự án định nghĩa và đoạn reflection trong `main()` xử lý.

Thậm chí một annotation **được Java SE định nghĩa** vẫn có thể được thư viện ngoài quan tâm, và annotation **được thư viện ngoài định nghĩa** vẫn tuân theo mọi quy tắc cú pháp annotation của Java.

### 7.3. Retention không quyết định ai “chạy” annotation

`@Retention(RUNTIME)` chỉ nói metadata có thể được duy trì để đọc qua reflection khi chạy. Nó **không kích hoạt trình chạy test, hệ thống dependency injection, validation hay transaction**.

Tương tự, `@Retention(SOURCE)` không làm annotation “vô dụng”: annotation SOURCE có thể quan trọng với compiler hoặc công cụ trong giai đoạn xử lý mã nguồn.

## 8. Sai lầm thường gặp

**1. Thấy `@Test` là cho rằng có sẵn trong JDK.** JDK không tự cung cấp JUnit Jupiter. Hãy kiểm tra `org.junit.jupiter.api.Test` và các test dependencies.

**2. Thấy `javax` là cho rằng thuộc Java SE; thấy `jakarta` là cho rằng Java compiler tự xử lý.** Phải xác định chính xác class nằm trong module/JAR nào. Jakarta EE và Java SE là các nền tảng khác nhau.

**3. Thêm `@Component` rồi chờ Java tự tạo bean.** Cần Spring context và cấu hình phát hiện bean thích hợp.

**4. Thêm `@NotNull` rồi tin đối tượng không bao giờ được null.** Đây là khai báo ràng buộc, cần bộ xử lý validation phù hợp; field vẫn có thể chứa null nếu không có cơ chế kiểm tra.

**5. Cho rằng mọi thư viện ngoài hoạt động bằng reflection.** Lombok là ví dụ của quá trình xử lý/tích hợp vào compiler. Annotation processor cũng có thể đọc metadata ở giai đoạn biên dịch.

**6. Nghĩ annotation không đọc được bằng reflection là thư viện ngoài hoặc vô hiệu.** `@Override` thuộc Java SE nhưng có SOURCE retention; nhiều annotation custom/third-party cũng không lưu tới runtime.

**7. Nhầm `@Retention`, `@Target` với annotation từ thư viện khai báo.** Chúng là meta-annotation chuẩn Java SE, bất kể annotation mà chúng mô tả được tự định nghĩa hay nằm trong một thư viện.

**8. Cho rằng “biên dịch được” tương đương “được framework xử lý”.** Có dependency là điều kiện ban đầu; còn phải có test engine, bean scanning, interceptor, validator hoặc cấu hình thích hợp cho từng công dụng.

## 9. Bài tập tự kiểm tra

1. Với `@Override`, `@Deprecated`, `@Retention`, `@Test` của JUnit, `@Transactional` của Spring và `@Getter` của Lombok, hãy ghi **tên đầy đủ**, **nguồn cung cấp**, **bộ xử lý chính** và **có cần dependency ngoài JDK không**.
2. Trong chương trình `AnnotationOriginDemo`, thử thêm `@Override` lên `hello()` (một static method không override). Dự đoán lỗi biên dịch và giải thích vì sao lỗi xuất hiện dù `@Override` không được reflection đọc.
3. Xóa `@Retention(RetentionPolicy.RUNTIME)` khỏi định nghĩa `@Purpose`, rồi quan sát kết quả đọc bằng reflection. Quy tắc mặc định là CLASS retention; hãy lý giải vì sao `getAnnotation(Purpose.class)` khi đó không còn cung cấp annotation. (Hãy sửa code trước khi gọi `.value()` để tránh dereference null.)
4. Cho một dự án có `import jakarta.validation.constraints.NotNull` nhưng chưa gọi validation và không dùng framework tích hợp validator: giải thích vì sao giá trị null vẫn có thể được gán, cũng như điều kiện để ràng buộc được kiểm tra.
5. Trong một class test dùng JUnit, thử bỏ JUnit dependency và đọc thông báo compiler. Sau khi thêm dependency, tìm cách chạy test thông qua JUnit Platform thay vì gọi `java` trực tiếp vào class test.

**Ghi nhớ khi áp dụng:** Java SE xác định cú pháp chung và một tập annotation chuẩn. Các thư viện có thể tự định nghĩa annotation bằng chính ngôn ngữ đó. Muốn hiểu một annotation, luôn tra **kiểu được import, nơi nó được đóng gói, `@Target`/`@Retention` và thành phần thực sự xử lý nó**. Đó mới là cơ sở để biết dự án cần dependency gì và annotation tạo ra hiệu quả nào.
