# Chuyển đổi null, chuỗi rỗng và kiểu nguyên thủy với Spring ConversionService

> **Chủ đề:** Spring Framework – validation-data-binding  
> **Nhóm:** ConversionService  
> **Phạm vi:** Phân biệt source `null`, chuỗi rỗng, chuỗi chỉ có khoảng trắng và giá trị số/boolean; hành vi converter mặc định; primitive và wrapper; xử lý trong Spring MVC, JavaBeans và DataBinder. Ví dụ dùng Java 17 và Spring Framework 6.2.x.

## 1. Vì sao ba trạng thái này dễ bị nhầm?

Trong Java và HTTP, những giá trị sau không đồng nghĩa:

- `null`: không có object tham chiếu.
- `""`: một đối tượng String có độ dài bằng 0.
- `"   "`: một String chứa ký tự khoảng trắng; `isEmpty()` là false nhưng `isBlank()` là true.
- `0` và `false`: giá trị cụ thể, không có nghĩa là client không gửi.
- Không gửi parameter/property: nguồn không cung cấp key đó.

Ví dụ:

```text
GET /search                    -> parameter q vắng mặt
GET /search?q=                 -> q có mặt, value là ""
GET /search?q=%20%20           -> q có mặt, value là hai dấu cách
GET /search?page=0             -> page có value "0"
GET /search?enabled=false      -> enabled có value "false"
```

Với JSON:

```json
{}
{"nickname": ""}
{"nickname": null}
{"enabled": false}
{"page": 0}
```

Property bị bỏ qua khi deserialize có thể giữ initializer hoặc giá trị constructor; property explicit null có thể ghi đè thành null tùy mapper/creator. Vì vậy không mặc định JSON missing và JSON null là một trạng thái.

Bài học này giúp bạn giải thích:
1. `ConversionService` làm gì khi source là null.
2. Converter chuẩn xử lý empty/blank khác nhau ra sao.
3. Khác biệt giữa `Integer` và `int`, `Boolean` và `boolean`.
4. Vì sao Spring MVC có xử lý đặc biệt khi conversion trả null cho tham số controller.
5. Cách thiết kế API để phân biệt missing, empty, zero và false.

## 2. ConversionService xử lý source null riêng

API tổng quát:

```java
public interface ConversionService {
    boolean canConvert(Class<?> sourceType, Class<?> targetType);
    <T> T convert(Object source, Class<T> targetType);
}
```

`ConversionService.convert(...)` nhận source có thể null. Khi source null, `GenericConversionService` xử lý ở nhánh null-source (`convertNullSource(...)`), trước khi gọi converter thông thường.

Với implementation mặc định của Spring:
- Phần lớn target type nhận kết quả null.
- Target là `Optional` nhận `Optional.empty()`.
- Target primitive không thể biểu diễn null; conversion thất bại (`ConversionFailedException`).

Ví dụ:

```java
DefaultConversionService service = new DefaultConversionService();

Integer number = service.convert(null, Integer.class); // null
Optional<?> value = service.convert(null, Optional.class); // Optional.empty()
```

Contract của Spring `Converter<S,T>` bảo đảm tham số truyền vào `convert(S source)` là non-null. Do đó null source được `ConversionService` xử lý trước; custom converter thông thường không nên dựa vào việc nhận null.

**Null source khác empty String source.** `convert(null, Integer.class)` đi qua nhánh null-source. `convert("", Integer.class)` có source thật là một String rỗng nên converter `String -> Number` được gọi và tự áp dụng quy tắc riêng.

## 3. Empty String phụ thuộc vào converter và target type

Không có quy tắc chung rằng mọi chuỗi rỗng đều trở thành null. Một số converter mặc định minh họa:

| Source → target | `""` | `"   "` | Ghi chú |
| --- | --- | --- | --- |
| `String -> String` | `""` | `"   "` | Chuỗi được giữ nguyên |
| `String -> Integer/Long` | `null` | Không dùng như missing; parse có thể thất bại | Converter số kiểm tra empty String, không có blank-normalization chung |
| `String -> Boolean` | `null` | `null` sau trim | Chấp nhận tập token true/false cụ thể |
| `String -> Character` | `null` | Ký tự dấu cách | Một ký tự hợp lệ |
| `String -> UUID` | `null` | `null` nếu không có text | Converter UUID kiểm tra text trước khi parse |
| `String -> custom value` | Do converter quyết định | Do converter quyết định | Phải định nghĩa contract |

Các kết quả trên là hành vi của converter cụ thể trong `DefaultConversionService`, không phải chính sách tổng quát cho mọi kiểu. Nếu muốn blank được xử lý khác, hãy cấu hình converter/formatter hoặc chuẩn hóa tại ranh giới phù hợp.

### 3.1. String sang Number

Spring có converter factory cho các kiểu số. Converter tạo ra kiểm tra `source.isEmpty()`; nếu true, trả null. Nếu không rỗng, nó parse giá trị sang target number.

```java
Integer empty = service.convert("", Integer.class); // null
Integer zero = service.convert("0", Integer.class);  // 0
Integer one = service.convert("1", Integer.class);   // 1
```

`""` và `"0"` hoàn toàn khác nhau. Chuỗi rỗng có thể biểu diễn trường chưa nhập; số 0 là một giá trị cụ thể. Nếu nghiệp vụ cấm 0, hãy dùng validation như `@Positive` hoặc `@Min(1)`, không đổi 0 thành null trong converter.

Converter số kiểm tra empty String, không đồng nhất mọi chuỗi chỉ có whitespace với empty. Nếu API cần quy tắc cho `"   "`, hãy trim/validate có chủ đích và viết test, không dựa vào lỗi parser như một chính sách nghiệp vụ.

### 3.2. String sang Boolean

Converter Boolean chuẩn:
1. Trim whitespace.
2. Chuyển lowercase với `Locale.ROOT`.
3. Nhận các token true: `"true"`, `"on"`, `"yes"`, `"1"`.
4. Nhận các token false: `"false"`, `"off"`, `"no"`, `"0"`.
5. Chuỗi rỗng sau trim trả null; token khác gây conversion failure.

| Input | Kết quả Boolean |
| --- | --- |
| `"true"`, `"yes"`, `"1"` | `true` |
| `"false"`, `"off"`, `"no"`, `"0"` | `false` |
| `""` | `null` |
| `"   "` | `null` sau trim |
| `"enabled"` | Conversion failure |

`Boolean.FALSE` khác null. Nếu code cần phân biệt “client không chọn” với “client chủ động tắt”, hãy dùng wrapper `Boolean`.

### 3.3. String sang Character và UUID

Converter Character trả null cho chuỗi rỗng; độ dài một ký tự thì trả character đó; độ dài lớn hơn một thì báo lỗi. Vì thế `" "` là một ký tự dấu cách, không phải empty.

Converter UUID kiểm tra chuỗi có text rồi trim trước khi parse. Empty/blank có thể trở thành null; chuỗi có nội dung nhưng sai định dạng sẽ gây lỗi. Đây là quy tắc của UUID converter cụ thể, không áp dụng cho mọi target.

## 4. Primitive và wrapper: khác biệt quyết định

Primitive không thể chứa null; wrapper là object nên có thể:

| Primitive | Wrapper | Có thể chứa null? |
| --- | --- | --- |
| `int` | `Integer` | Chỉ Integer |
| `long` | `Long` | Chỉ Long |
| `boolean` | `Boolean` | Chỉ Boolean |
| `double` | `Double` | Chỉ Double |

Ví dụ:

```java
int count = 0;                  // Giá trị mặc định của Java
Integer optionalCount = null;   // Biểu diễn được vắng mặt

boolean enabled = false;
Boolean optionalEnabled = null;
```

Khi object mới tạo, field primitive có default value của Java: số nguyên 0, boolean false, số thực 0.0. Do đó primitive không cho biết client có thực sự gửi dữ liệu hay không. Nếu cần phân biệt missing với zero/false, hãy dùng wrapper hoặc kiểu biểu diễn presence riêng.

### 4.1. ConversionService với primitive target

Với wrapper, null có thể được trả về:

```java
Integer boxed = service.convert(null, Integer.class);
// boxed == null
```

Với primitive, null không thể được biểu diễn:

```java
int primitive = service.convert(null, int.class);
// ConversionFailedException
```

Đây là quy tắc ở cấp ConversionService. Không suy ra mọi pipeline Spring MVC/DataBinder đều trả cùng exception; các pipeline này có thể có xử lý riêng.

### 4.2. Spring MVC xử lý null sau conversion

Đối với named-value arguments như `@RequestParam`, `@RequestHeader`, `@PathVariable`, `@CookieValue`, Spring MVC có bước xử lý sau conversion. Nếu giá trị cuối cùng là null:
- Primitive `boolean` được xử lý thành `false`.
- Primitive khác (ví dụ `int`) gây lỗi vì không thể nhận null.
- Wrapper như `Integer` có thể nhận null khi tham số được khai báo cho phép null, thường qua `required = false` hoặc `@Nullable`.
- Nếu tham số là required và value thành null sau conversion, Spring xem như giá trị thiếu và phát sinh missing-value exception tương ứng.

Ví dụ wrapper optional:

```java
@GetMapping("/filter")
public String filter(
        @RequestParam(required = false) Integer page,
        @RequestParam(required = false) Boolean enabled) {
    return "page=" + page + ", enabled=" + enabled;
}
```

Với `/filter?page=&enabled=`, converter số/boolean có thể trả null và wrapper nhận null theo argument policy.

Ví dụ primitive:

```java
@GetMapping("/filter-primitive")
public String filter(
        @RequestParam(required = false) int page,
        @RequestParam(required = false) boolean enabled) {
    return "page=" + page + ", enabled=" + enabled;
}
```

Kết quả null cho `boolean` được xử lý thành false; null cho `int` không thể biểu diễn và gây lỗi. Không khai báo `required=false` trên primitive số với kỳ vọng method nhận null. Dùng `Integer` nếu muốn biểu diễn trạng thái chưa có giá trị.

Nếu khai báo `@RequestParam(defaultValue = "20")`, Spring áp dụng default khi parameter thiếu hoặc rỗng theo quy tắc annotation. Vì thế client gửi `?page=` có thể nhận 20, giống trường hợp parameter không xuất hiện. Chỉ chọn defaultValue nếu hợp đồng API thực sự muốn hai tình huống có cùng nghĩa.

## 5. Bảng tổng hợp theo input và target

Bảng sau mô tả converter mặc định; cột MVC chỉ nói về named-value argument khi conversion đã trả null.

| Input | `ConversionService -> Integer` | `-> Boolean` | MVC `Integer`, optional | MVC `int`, optional |
| --- | --- | --- | --- | --- |
| Source null | null | null | null | Lỗi primitive |
| `""` | null | null | null | Lỗi primitive |
| `"   "` | Không dùng như missing; có thể lỗi parse | null sau trim | null nếu conversion trả null | Lỗi nếu conversion trả null |
| `"0"` | 0 | false | 0 | 0 |
| `"false"` | Number conversion failure | false | Number conversion failure | Number conversion failure |
| `"abc"` | Number conversion failure | Boolean conversion failure | Binding/conversion error | Binding/conversion error |

`String` target giữ nguyên empty String. UUID, Character và custom value types có quy tắc riêng. Khi đọc bảng, luôn xác định source type, target type, converter và pipeline.

## 6. Ví dụ Java 17 chạy được với Maven

Tạo project:

```text
conversion-null-demo/
  pom.xml
  src/main/java/demo/NullEmptyConversionDemo.java
```

### pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>conversion-null-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### NullEmptyConversionDemo.java

```java
package demo;

import java.util.UUID;

import org.springframework.core.convert.ConversionException;
import org.springframework.core.convert.support.DefaultConversionService;

public final class NullEmptyConversionDemo {

    public static void main(String[] args) {
        DefaultConversionService service =
                new DefaultConversionService();

        Integer nullNumber = service.convert(null, Integer.class);
        Integer emptyNumber = service.convert("", Integer.class);
        Integer zero = service.convert("0", Integer.class);

        Boolean emptyBoolean = service.convert("", Boolean.class);
        Boolean blankBoolean = service.convert("   ", Boolean.class);
        Boolean falseBoolean = service.convert("false", Boolean.class);
        Boolean zeroBoolean = service.convert("0", Boolean.class);

        Character emptyCharacter = service.convert("", Character.class);
        UUID emptyUuid = service.convert("", UUID.class);
        String emptyString = service.convert("", String.class);

        System.out.println("nullToInteger=" + nullNumber);
        System.out.println("emptyToInteger=" + emptyNumber);
        System.out.println("zeroToInteger=" + zero);
        System.out.println("emptyToBoolean=" + emptyBoolean);
        System.out.println("blankToBoolean=" + blankBoolean);
        System.out.println("falseToBoolean=" + falseBoolean);
        System.out.println("zeroToBoolean=" + zeroBoolean);
        System.out.println("emptyToCharacter=" + emptyCharacter);
        System.out.println("emptyToUuid=" + emptyUuid);
        System.out.println("emptyStringLength=" + emptyString.length());

        try {
            service.convert(null, int.class);
            System.out.println("nullToInt=unexpected-success");
        } catch (ConversionException ex) {
            System.out.println("nullToInt=ConversionException");
        }
    }
}
```

Chạy bằng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.NullEmptyConversionDemo
```

Stdout:

```text
nullToInteger=null
emptyToInteger=null
zeroToInteger=0
emptyToBoolean=null
blankToBoolean=null
falseToBoolean=false
zeroToBoolean=false
emptyToCharacter=null
emptyToUuid=null
emptyStringLength=0
nullToInt=ConversionException
```

Chương trình cần dependency `spring-core`; chỉ dùng `javac` không có Spring trong classpath sẽ không biên dịch. Output minh họa `DefaultConversionService` của Spring 6.2.x. Nếu đăng ký custom converter hoặc thay implementation, hành vi có thể khác.

## 7. Viết custom Converter: phải định nghĩa blank/null

Contract của Spring `Converter<S,T>` đảm bảo source truyền vào `convert` là non-null. Vì vậy:
- Không cần xử lý null reference như thể converter chuẩn nhận nó.
- Vẫn phải quyết định empty/blank có hợp lệ không.
- Không tự động trả null cho chuỗi rỗng nếu điều đó có thể che lỗi dữ liệu.
- Nếu blank nghĩa là “không nhập”, hãy thể hiện rõ semantics ở DTO/application layer.

Ví dụ value object:

```java
package demo;

public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || !value.matches("CUS-[A-Z0-9]{5}")) {
            throw new IllegalArgumentException("Invalid customer code");
        }
    }
}
```

Converter:

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        // source non-null theo Converter contract.
        String normalized = source.strip().toUpperCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    "Customer code must not be blank");
        }

        return new CustomerCode(normalized);
    }
}
```

Khi dùng converter này, ConversionService xử lý null source trước; nếu source là `""`, converter được gọi và từ chối blank. Cách làm giữ rõ sự khác nhau giữa không có object và client gửi String rỗng.

Nếu value object optional, hãy để field reference nullable/Optional theo hợp đồng rồi quy định rõ khi nào blank được xem là missing. Không tạo value object giả có `value == null`.

## 8. Optional value và validation

### 8.1. Giá trị bắt buộc

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record PagingRequest(
        @NotNull
        @Min(1)
        Integer page
) {}
```

`@NotNull` phát hiện null; `@Min(1)` từ chối zero hoặc số âm. `@Min` một mình không coi null là lỗi, nên hai constraint bổ sung cho nhau.

### 8.2. Optional nhưng vẫn phân biệt zero/false

```java
public record SearchOptions(
        Integer page,
        Boolean includeArchived
) {}
```

Cách diễn giải:
- `page == null`: không chỉ định.
- `page == 0`: client chỉ định zero; validation có thể từ chối nếu page bắt đầu từ 1.
- `includeArchived == null`: chưa lựa chọn; policy có thể áp dụng default.
- `includeArchived == false`: client tường minh tắt.

Đừng gộp null và zero nếu zero có semantics riêng.

### 8.3. Optional parameter trong MVC

```java
@GetMapping("/items")
public String items(
        @RequestParam(required = false) Integer page,
        @RequestParam(required = false) Boolean includeArchived) {
    return "page=" + page + ", archived=" + includeArchived;
}
```

Dùng wrapper để nhận null. Nếu hợp đồng muốn default khi thiếu/rỗng:

```java
@GetMapping("/items-default")
public String itemsDefault(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "false") boolean includeArchived) {
    return "page=" + page + ", archived=" + includeArchived;
}
```

`defaultValue` là một lựa chọn contract; nó có thể khiến parameter thiếu và rỗng có cùng kết quả. Nếu cần phân biệt hai tình huống, giữ presence/value riêng thay vì dùng defaultValue.

## 9. Primitive default của Java không phải default input

Ví dụ JavaBean:

```java
public class UpdateOptions {
    private boolean enabled;
    private int retryCount;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getRetryCount() { return retryCount; }
    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
```

Ngay sau `new UpdateOptions()`, `enabled` là false và `retryCount` là 0 do Java khởi tạo primitive. Điều này không chứng minh client đã gửi false hoặc 0. Nếu form bỏ qua các field, object có thể vẫn mang default Java.

Wrapper cho phép phân biệt:

```java
private Boolean enabled;
private Integer retryCount;
```

Khi chưa được gán, hai field wrapper là null. Đây thường là lựa chọn phù hợp hơn cho input DTO nếu “không gửi” cần được phân biệt với “tắt” hoặc “0”.

`@NotNull` trên primitive không giúp phát hiện missing: primitive luôn có một giá trị. Hãy dùng wrapper và constraint nếu cần bắt buộc phải có input.

## 10. DataBinder và property binding

DataBinder/BeanWrapper dùng conversion khi gán property. Kết quả tùy target type:

- Property `String` giữ empty string.
- Property `Integer` có thể nhận null sau khi empty String được đổi thành null.
- Property primitive không thể lưu null; null-to-primitive không hợp lệ, có thể được báo như binding/type mismatch tùy pipeline.
- Custom PropertyEditor/Formatter có thể quy định cách xử lý empty khác DefaultConversionService.

Ví dụ DTO:

```java
public class FilterForm {
    private Integer page;
    private String keyword;

    public Integer getPage() { return page; }
    public void setPage(Integer page) { this.page = page; }

    public String getKeyword() { return keyword; }
    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }
}
```

Nếu input là `page=""`, converter số có thể trả null. Nếu input là `keyword=""`, String giữ nguyên empty. Chọn validation phù hợp: `@NotNull` nếu page bắt buộc; `@NotBlank` nếu keyword phải có nội dung.

Với primitive property, không giả định null tự đổi thành 0. Hãy test chính xác property type và binder đang dùng. Nếu cần default page 1, đặt default trong DTO constructor/initializer hoặc application service theo hợp đồng, thay vì phụ thuộc side effect conversion.

## 11. JSON null, missing và primitive

JSON body thường được đọc qua `HttpMessageConverter` như Jackson, không phải cùng pipeline query/form của WebDataBinder.

Các điểm cần kiểm soát:
- Property missing có thể giữ field initializer hoặc giá trị constructor.
- Property explicit null có thể gán null cho wrapper/reference.
- Primitive không chứa null; xử lý JSON null/missing phụ thuộc cấu hình Jackson và creator/property.
- Cấu hình như `FAIL_ON_NULL_FOR_PRIMITIVES` có thể làm null JSON vào primitive trở thành lỗi.
- Record/constructor DTO có thể nhận null cho cả missing lẫn explicit null nếu mapper không giữ presence riêng.

Nếu API cần phân biệt `{}` với `{"page":null}`, hãy dùng DTO/deserializer/JSON presence model có thể giữ thông tin đó. Không dùng quy tắc `@RequestParam` để suy ra `@RequestBody`.

## 12. Phân biệt conversion và validation

Conversion trả lời: “giá trị source có thể được chuyển sang target type không?”. Validation trả lời: “giá trị sau khi bind có thỏa ràng buộc không?”.

Ví dụ:
- `"0"` → `Integer(0)`: conversion thành công.
- Nếu page phải bắt đầu từ 1, `@Min(1)` từ chối.
- `""` → null với converter số.
- Nếu page bắt buộc, `@NotNull` từ chối null.
- `"abc"` → conversion error; validation thường không nhận được một Integer hợp lệ để kiểm tra.

Controller JSON minh họa:

```java
@PostMapping("/paging")
public String paging(@Valid @RequestBody PagingRequest request) {
    return "page=" + request.page();
}
```

Đoạn này minh họa Bean Validation trên DTO sau deserialization. Jackson conversion vẫn là pipeline riêng; `@Valid` không biến lỗi parse JSON thành business rule.

## 13. Ma trận tình huống API

| Hợp đồng | Kiểu Java nên chọn | Cách xử lý |
| --- | --- | --- |
| Page bắt buộc | `Integer` | `@NotNull` + `@Min(1)` |
| Page optional, zero có nghĩa riêng | `Integer` | null = không gửi; 0 được validate riêng |
| Boolean optional, false có nghĩa riêng | `Boolean` | null = chưa chọn; false = tắt |
| Boolean luôn mặc định false | `boolean` hoặc wrapper có default rõ ràng | Quyết định default trong contract/service |
| String phải có nội dung | `String` | `@NotBlank` |
| String optional, empty khác missing | `String` + presence tracking | Giữ key presence/value |
| Value object bắt buộc | Reference type | Converter + invariant + `@NotNull` |
| Value object optional | Reference/Optional theo contract | Quy định blank có phải missing hay lỗi |

## 14. Lỗi phổ biến

**1. Coi null và empty là một.** Null source đi qua nhánh riêng; empty String đi qua converter.

**2. Nghĩ mọi chuỗi rỗng thành null.** String, Number, Boolean, Character và UUID có hành vi riêng.

**3. Dùng primitive cho input optional.** Không giữ được thông tin missing; dùng wrapper.

**4. Coi 0/false là thiếu.** Đây có thể là giá trị client gửi tường minh.

**5. Mong Converter xử lý null source.** Spring xử lý null ở ConversionService trước; converter thường nhận non-null source.

**6. Nghĩ null tự đổi thành 0.** ConversionService không thể biểu diễn null bằng primitive; MVC có special case boolean false, primitive số lỗi.

**7. Dùng `required=false` với primitive int để nhận null.** Dùng Integer.

**8. Dùng defaultValue trong khi vẫn cần phân biệt empty và missing.** defaultValue có thể áp dụng cho cả hai.

**9. Đặt `@NotNull` trên primitive.** Primitive không thể null.

**10. Dùng validation để xử lý sai format.** Binding/conversion failure phải được xử lý riêng.

**11. Đánh đồng JSON với query/form.** Jackson và WebDataBinder là hai pipeline khác nhau.

**12. Bỏ qua whitespace-only trong test.** `""` và `"   "` có thể cho kết quả khác nhau tùy converter.

## 15. Checklist kiểm thử

1. Xác định contract cho missing, null, empty, blank, zero và false.
2. Chọn primitive/wrapper theo việc field có thể vắng mặt không.
3. Kiểm tra converter cụ thể của source/target pair.
4. Với custom converter, định nghĩa blank bị từ chối, chuẩn hóa hay trả null.
5. Trong MVC, xác định `required`, `defaultValue`, `@Nullable` và primitive behavior.
6. Chạy Bean Validation sau binding để kiểm tra null, range và blank.
7. Tách binding error khỏi business rejection.
8. Test query/form riêng với JSON body.
9. Test cả zero/false lẫn missing/empty.
10. Test trên đúng Spring version và ConversionService registry của ứng dụng.

### Test matrix tối thiểu

| Test | Kết quả cần xác minh |
| --- | --- |
| `convert(null, Integer.class)` | null |
| `convert("", Integer.class)` | null với converter số mặc định |
| `convert("0", Integer.class)` | 0 |
| `convert("", Boolean.class)` | null |
| `convert("  ", Boolean.class)` | null sau trim |
| `convert("false", Boolean.class)` | false |
| `convert("0", Boolean.class)` | false |
| `convert("", String.class)` | Empty String |
| `convert(null, int.class)` | Conversion failure |
| MVC optional `Integer` khi parameter empty | Wrapper nhận null nếu conversion trả null |
| MVC optional `int` khi conversion trả null | Exception vì primitive không nhận null |
| MVC optional `boolean` khi conversion trả null | false theo named-value resolver |
| JSON missing và explicit null | Xác minh riêng theo Jackson/DTO policy |

**Ghi nhớ:** null là không có object; empty String là một String độ dài 0; blank String chứa ký tự nhưng không có text; primitive không chứa null còn wrapper có thể. Spring xử lý chúng dựa trên target type, converter và pipeline. Thiết kế contract rõ ràng, chọn đúng kiểu Java và kiểm thử đủ trạng thái.

## Tài liệu tham khảo

- [Spring Framework 6.2 – Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html): ConversionService, null-source conversion và Converter contract.
- [Spring Framework 6.2 – MVC Controller Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/typeconversion.html): empty String thành null sau conversion và required/nullable arguments.
- [ConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/convert/ConversionService.html): API conversion với source có thể null.
- [GenericConversionService source](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/GenericConversionService.java): null-source branch.
- [StringToBooleanConverter source](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/StringToBooleanConverter.java): boolean tokens, trim và blank-to-null.
- [Spring MVC named-value argument resolver source](https://github.com/spring-projects/spring-framework/blob/main/spring-web/src/main/java/org/springframework/web/method/annotation/AbstractNamedValueMethodArgumentResolver.java): primitive boolean và lỗi với primitive khác khi kết quả null.
