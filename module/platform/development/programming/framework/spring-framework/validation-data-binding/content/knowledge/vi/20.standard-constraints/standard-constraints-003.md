# @Size cho chuỗi, mảng, Collection và Map trong Bean Validation

## 1. Mục tiêu và quy tắc cốt lõi

`@Size` là một constraint chuẩn của **Jakarta Bean Validation** để yêu cầu **kích thước của một giá trị nằm trong khoảng từ `min` đến `max` (bao gồm hai đầu mút)**. Trong ứng dụng Spring Framework, constraint này thường được đặt trên DTO nhận request, bean cấu hình, đối tượng nghiệp vụ hoặc tham số phương thức được Bean Validation thực thi.

Import dùng với Spring Framework 6 và Spring Boot 3:

~~~java
import jakarta.validation.constraints.Size;
~~~

Ví dụ cơ bản:

~~~java
@Size(min = 3, max = 20)
private String username;

@Size(min = 1, max = 5)
private List<String> roles;

@Size(max = 10)
private byte[] signature;

@Size(min = 1, max = 4)
private Map<String, String> metadata;
~~~

Điều cần nhớ: **`@Size` đo kích thước của chính giá trị được gắn annotation, không tự kiểm tra nội dung hoặc từng phần tử bên trong giá trị đó.** Nếu muốn kiểm tra từng phần tử, hãy viết constraint ở type argument hoặc dùng cascade `@Valid` cho bean con.

| Kiểu được khai báo | `@Size` đếm gì? | Ví dụ `@Size(min = 2, max = 4)` |
| --- | --- | --- |
| `String`, `StringBuilder`, `CharSequence` | `length()` của chuỗi ký tự, theo ngữ nghĩa Java | `"AB"` đạt, `"A"` không đạt. |
| `String[]`, `int[]`, `byte[]`, mảng khác | `array.length`, số phần tử của mảng | `new int[]{1,2,3}` đạt. |
| `List`, `Set` hoặc lớp triển khai `Collection` | `collection.size()` | List có 3 phần tử đạt, Set có 5 phần tử không đạt. |
| `Map` | `map.size()`, số **entry** (cặp key–value) | Map có 2 entry đạt. |
| `null` ở bất kỳ kiểu hợp lệ trên | Được xem là **hợp lệ theo `@Size`** | Cần thêm `@NotNull` nếu bắt buộc có giá trị. |

Các quy tắc này được quy định bởi chuẩn Jakarta Bean Validation. Provider như Hibernate Validator thực thi chúng khi chạy `Validator.validate(bean)` hoặc khi Spring kích hoạt validation phù hợp.

### Giá trị biên và mặc định

~~~java
@Size(min = 2, max = 4) // 2, 3 và 4 đều đạt
@Size(min = 2)          // Giới hạn trên mặc định: Integer.MAX_VALUE
@Size(max = 4)          // Giới hạn dưới mặc định: 0
@Size                   // min=0, max=Integer.MAX_VALUE
~~~

Hai tham số `min` và `max` là `int`:

- `min` mặc định **0**.
- `max` mặc định **`Integer.MAX_VALUE`**.
- Kích thước được chấp nhận khi `min <= size <= max`.
- Giá trị cấu hình hợp lý phải có `min >= 0` và `max >= min`. Khai báo sai các ràng buộc biên là vấn đề cấu hình, không phải “lỗi người dùng nhập dữ liệu” thông thường.
- `@Size(max = 0)` chỉ chấp nhận giá trị **có kích thước 0** hoặc `null`; nó không đồng nghĩa với `@Null`.
- `@Size(min = 1)` từ chối một giá trị rỗng không null, nhưng **vẫn cho phép null**.

## 2. Cách Bean Validation thực hiện @Size

Annotation là metadata gắn lên field, getter, parameter, return value hoặc type-use. Tự viết annotation không đồng nghĩa tự động chạy kiểm tra.

~~~text
DTO / domain object có @Size
          |
          | Validator.validate(bean)
          v
 Bean Validation provider
          |
          | Xác định kiểu và validator phù hợp
          | Giá trị null? -> hợp lệ cho @Size
          | Không null? -> tính length/size
          v
 So sánh min <= size <= max
        /                  \
      đúng                 sai
       |                     |
Không phát sinh          Tạo một
vi phạm @Size            ConstraintViolation
       \                     /
        \                   /
         Set<ConstraintViolation<T>>
~~~

Khi validation thành công đối với mọi constraint trong phạm vi đang xét, `Validator.validate(...)` trả tập rỗng. Khi thất bại, tập có thông tin như property path, message, invalid value và descriptor.

Nếu chỉ cần kiểm tra độ dài trực tiếp trong Java, `String.length()` hoặc `Collection.size()` là cách bình thường; lợi ích `@Size` nằm ở chỗ **khai báo ràng buộc một lần**, để framework/provider thực thi nhất quán trên nhiều đường xử lý và cung cấp lỗi cấu trúc.

## 3. @Size trên String và CharSequence

### 3.1. Đếm độ dài, không đếm chữ có nghĩa

~~~java
@Size(min = 3, max = 8, message = "Tên cần từ {min} đến {max} đơn vị")
private String displayName;
~~~

Khi được validate, provider đánh giá chiều dài chuỗi. Với `String` Java, `length()` trả **số đơn vị mã UTF-16**, không bảo đảm là số Unicode code point hoặc số ký tự người dùng thấy (grapheme cluster). Đây là điều quan trọng khi dữ liệu có emoji hoặc dấu kết hợp.

| Giá trị chuỗi | `String.length()` | Với `@Size(min=3,max=8)` |
| --- | ---: | --- |
| `"An"` | 2 | Không đạt |
| `"Anh"` | 3 | Đạt |
| `"Nguyen"` | 6 | Đạt |
| `"123456789"` | 9 | Không đạt |
| `""` | 0 | Không đạt |
| `"   "` | 3 | **Đạt**: ba khoảng trắng vẫn có độ dài 3 |
| `null` | Không áp dụng `length()` | **Đạt theo `@Size`** |

Với một emoji ngoài Basic Multilingual Plane, chẳng hạn `"🙂"`:

~~~java
System.out.println("🙂".length());              // 2
System.out.println("🙂".codePointCount(0, 2));  // 1
~~~

Đây là các câu lệnh Java 17 có thể đặt trong một phương thức. Kết quả lần lượt là `2` và `1`: một emoji đơn có thể chiếm **hai đơn vị UTF-16**. `@Size(max=1)` trên String chỉ gồm emoji này sẽ không đạt khi dùng cách tính độ dài Java thông thường. Các chuỗi Unicode có ký tự tổ hợp còn có thể có cách đếm khác với số ký tự người dùng nhìn thấy.

**Khi nghiệp vụ yêu cầu số ký tự người dùng nhìn thấy**, ví dụ tối đa 30 grapheme cluster trong tên, `@Size` có thể chưa đúng ngữ nghĩa. Cần định nghĩa chuẩn đếm rồi viết custom constraint hoặc xử lý phù hợp, có xét Unicode normalization và quy tắc phân đoạn grapheme. Không dùng `String.length()` như một thước đo “số chữ” tuyệt đối.

### 3.2. Khoảng trắng được tính

`@Size` không trim String trước khi đếm. Chuỗi `"   "` có độ dài 3; vì vậy `@Size(min=3)` có thể chấp nhận chuỗi này. Đối với tên bắt buộc có nội dung:

~~~java
@NotBlank
@Size(min = 3, max = 40)
private String fullName;
~~~

Cần import `jakarta.validation.constraints.NotBlank`. Khi đó:

- `@NotBlank` từ chối null, rỗng hoặc chỉ có khoảng trắng.
- `@Size` kiểm tra kích thước theo quy tắc độ dài.
- Cả hai **không tự biến đổi dữ liệu**. Nếu muốn cắt khoảng trắng đầu/cuối, hãy thực hiện normalization có chủ đích trước validation hoặc tại boundary được thiết kế.

Một chuỗi `"  Nam  "` có chiều dài 7 theo `@Size`, dù sau `strip()` còn `"Nam"` (3). Hãy thống nhất hợp đồng: validate **dữ liệu gốc** hay **dữ liệu đã chuẩn hóa**. Không tùy tiện strip mã định danh, password hoặc chữ ký số.

### 3.3. @Size không kiểm tra định dạng

`@Size(min=10, max=10)` không thể chứng minh chuỗi là một số điện thoại hợp lệ; nó chỉ chứng minh có 10 đơn vị UTF-16. Khi cần định dạng:

~~~java
@Size(min = 6, max = 12)
@Pattern(regexp = "[A-Z0-9]+")
private String productCode;
~~~

Với `@Pattern` cần import `jakarta.validation.constraints.Pattern`. Nếu giá trị null phải bị từ chối, thêm `@NotNull`/`@NotBlank` tùy hợp đồng. Một mã sai pattern nhưng đủ độ dài có thể vi phạm `@Pattern` mà không vi phạm `@Size`.

## 4. @Size trên mảng: số phần tử, không phải kích thước bộ nhớ

Mảng `T[]` và mảng primitive đều được hỗ trợ:

~~~java
@Size(min = 2, max = 5)
private String[] answerChoices;

@Size(min = 16, max = 32)
private byte[] keyMaterial;

@Size(max = 100)
private int[] scores;
~~~

Giải thích:

- Với `String[]`, đếm **số phần tử**, không cộng độ dài của từng String.
- Với `byte[]`, số phần tử bằng số byte của chính mảng, nhưng `@Size` không kiểm tra ý nghĩa mã hóa, chữ ký hay độ an toàn mật mã.
- Với `int[]`, đếm số `int`; không giới hạn giá trị từng phần tử và không đo byte bộ nhớ mà mảng tiêu thụ.
- Mảng `new String[3]` có kích thước 3 **ngay cả khi cả ba phần tử đều null**. `@Size(min=3,max=3)` vẫn đạt.

Ví dụ so sánh:

~~~java
String[] a = {"long text", ""};    // a.length == 2
byte[] b = new byte[4];            // b.length == 4
int[] c = new int[0];              // c.length == 0
~~~

Chỉ khi muốn kiểm tra nội dung phần tử mới cần thêm constraint khác. Ví dụ với String:

~~~java
@Size(min = 2, max = 4)
private String @NotNull [] choices;
~~~

Cú pháp type-use trên mảng dễ gây nhầm; cách rõ ràng hơn trong DTO khi cần validate từng phần tử là dùng `List<@NotBlank String>` cùng `@Size` trên List, như mục sau. Nếu dùng mảng, hãy kiểm tra vị trí annotation là trên **mảng** hay **kiểu phần tử** và xác nhận kết quả bằng `Validator.validate(...)`. Không suy rằng `@Size` trên mảng đã xác nhận mọi phần tử hợp lệ.

## 5. @Size trên Collection: List, Set và các triển khai

Với Java `Collection`, ràng buộc đo `collection.size()`.

~~~java
@Size(min = 1, max = 3)
private List<String> roleNames;

@Size(min = 2, max = 10)
private Set<Long> selectedIds;
~~~

Điểm cần phân biệt:

| Giá trị | Kích thước tính bởi `@Size` | Với `@Size(min=1,max=3)` |
| --- | ---: | --- |
| `List.of()` | 0 | Không đạt |
| `List.of("admin")` | 1 | Đạt |
| `List.of("A","B","C")` | 3 | Đạt |
| `List.of("A","B","C","D")` | 4 | Không đạt |
| `Set.of("A","B")` | 2 | Đạt |
| `null` | Không gọi `size()` | Đạt |
| List ba phần tử, một phần tử `null` | 3 | Đạt theo **constraint @Size** |

`Set` chỉ lưu các phần tử thực sự phân biệt theo hợp đồng `equals/hashCode`. Hai giá trị trùng trong `Set` không biến thành hai phần tử; `@Size` đo kích thước **sau khi Set đã hình thành**. Với `List`, giá trị trùng vẫn chiếm các vị trí khác nhau và được tính riêng.

### 5.1. Kích thước của Collection khác constraint trên phần tử

~~~java
@Size(min = 1, max = 3)
private List<@NotBlank String> tags;
~~~

Ở đây có **hai cấp kiểm tra**:

1. `@Size(min=1,max=3)` gắn trên **List**: giới hạn số tag.
2. `@NotBlank` gắn trên **mỗi phần tử String**: không cho phép String null, rỗng hoặc chỉ khoảng trắng.

Ví dụ `List.of("", "java", "spring", "api")` có bốn phần tử; nó vi phạm `@Size(max=3)`, đồng thời phần tử đầu vi phạm `@NotBlank`. Một request có thể nhận **hai violation** ở các vị trí khác nhau. Không kỳ vọng `@Size` tự phát hiện tag trống.

Kiểu giá trị có ràng buộc riêng có thể dùng:

~~~java
private List<@Size(min = 2, max = 20) String> labels;
~~~

Đây là `@Size` **trên từng String**, không giới hạn số phần tử của List. Muốn cả hai:

~~~java
@Size(min = 1, max = 10)
private List<@Size(min = 2, max = 20) String> labels;
~~~

Container element constraints của Bean Validation 2.0+/Jakarta Validation dùng type-use annotation. Nếu phần tử là **bean có annotation riêng**, chẳng hạn `OrderLine`, dùng `List<@Valid OrderLine>` để cascade vào bean con. Dù vậy `@Valid` không phải thay thế cho `@Size`, và chỉ kiểm tra số lượng phần tử không đủ xác nhận dữ liệu bên trong.

### 5.2. Collection rỗng, null và @NotEmpty

Khi yêu cầu phải có ít nhất một phần tử, hai cách có sắc thái khác nhau:

~~~java
@Size(min = 1)
private List<String> optionalList; // null vẫn được @Size chấp nhận

@NotEmpty
private List<String> mandatoryList; // null và list rỗng đều bị từ chối
~~~

Nếu cần giới hạn trên và bắt buộc không rỗng:

~~~java
@NotEmpty
@Size(max = 5)
private List<@NotBlank String> categories;
~~~

`@NotEmpty` đảm bảo danh sách có ít nhất một phần tử; `@Size(max=5)` giới hạn tối đa năm phần tử; `@NotBlank` kiểm tra từng String. Không cần lặp thêm `@Size(min=1)` nếu `@NotEmpty` đã thể hiện chính sách tối thiểu rõ ràng, trừ khi dự án có lý do quy ước riêng.

**Lưu ý về `Iterable`:** hợp đồng chuẩn của `@Size` liệt kê `Collection`, không bảo đảm áp dụng trực tiếp cho mọi lớp chỉ implement `Iterable` mà không implement `Collection`. Với một wrapper hoặc stream tùy biến, cần xem provider có hỗ trợ validator bổ sung hoặc tự viết constraint. Không gắn `@Size` lên một kiểu không hỗ trợ rồi giả định kết quả bằng cách đếm vòng lặp.

## 6. @Size trên Map: số entry, không phải độ dài key/value

~~~java
@Size(min = 1, max = 4)
private Map<String, String> preferences;
~~~

`Map.size()` đếm số cặp key–value:

| Map | `size()` | Với `@Size(min=1,max=4)` |
| --- | ---: | --- |
| `Map.of()` | 0 | Không đạt |
| `Map.of("theme","dark")` | 1 | Đạt |
| `Map.of("a","x", "b","y", "c","z", "d","w")` | 4 | Đạt |
| Map có năm entry | 5 | Không đạt |
| `null` | Không gọi `size()` | Đạt |

`@Size` **không kiểm tra** key có rỗng không, value có null không, độ dài value hay key chứa ký tự gì. Nếu cần ràng buộc cả Map và nội dung:

~~~java
@NotEmpty
@Size(max = 5)
private Map<@NotBlank String, @NotBlank String> labels;
~~~

Ràng buộc tương ứng:

- `@NotEmpty` trên Map: Map phải khác null và có entry.
- `@Size(max=5)` trên Map: tối đa năm entry.
- `@NotBlank` trên key và trên value: từng String trong các vị trí đó có nội dung không trắng.

Với key là `String` nhưng value là bean:

~~~java
@Size(max = 10)
private Map<@NotBlank String, @Valid Contact> contacts;
~~~

Đây là đoạn khai báo minh họa cần lớp `Contact` có constraint, `jakarta.validation.Valid` và các import. Bean Validation thực thi ràng buộc key và cascade sang các bean value khi `Validator.validate(...)` áp dụng, theo cấu hình nhóm tương ứng.

Đừng quên: một Map có thể từ chối key trùng/ghi đè key cũ. Sau khi tạo Map, `@Size` đo **số entry hiện có**, không đo số cặp người dùng đã gửi trước quá trình parse. Nếu API cần giới hạn số trường trong payload JSON *trước khi phân tích*, phải dùng giới hạn request parser/transport phù hợp; `@Size` trên DTO chỉ chạy khi đã có đối tượng Java.

## 7. @Size so với @NotNull, @NotEmpty, @NotBlank và các constraint khác

Đây là nguồn nhầm lẫn lớn nhất khi dùng ràng buộc chuẩn.

| Constraint | `null` có hợp lệ? | `""` (String rỗng) | `"   "` | List/Map rỗng |
| --- | --- | --- | --- | --- |
| `@Size(min=1)` | **Có** | Sai vì size=0 | Đúng vì size=3 | Sai vì size=0 |
| `@NotNull` | **Không** | Đúng | Đúng | Đúng |
| `@NotEmpty` | **Không** | Sai | Đúng | Sai |
| `@NotBlank` | **Không** | Sai | Sai | Không áp dụng chuẩn cho List/Map |

Chọn theo yêu cầu:

- **Giới hạn số lượng hoặc độ dài**: `@Size(min=..., max=...)`.
- **Bắt buộc có đối tượng** nhưng chấp nhận rỗng: `@NotNull`.
- **Bắt buộc có ít nhất một ký tự hoặc phần tử**: `@NotEmpty`, dùng cho CharSequence/Collection/Map/array.
- **Bắt buộc String có nội dung không toàn khoảng trắng**: `@NotBlank`, dùng cho CharSequence.
- **Kiểm tra pattern String**: `@Pattern`.
- **Kiểm tra giá trị số**: `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`, `@Digits` tùy trường hợp; `@Size` không phải constraint chuẩn cho `int` hoặc `BigDecimal`.

Ví dụ form đăng ký:

~~~java
@NotBlank
@Size(min = 3, max = 30)
private String username;

@NotNull
@Size(min = 2, max = 5)
private List<@NotBlank String> permissions;
~~~

Hai field có chính sách riêng: username phải có chữ thật và đủ dài; permissions phải có list và 2–5 phần tử, mỗi permission là String không trắng. Nếu thiết kế chấp nhận list null nhưng list hiện diện phải có 2–5 phần tử, chỉ dùng `@Size(min=2,max=5)` cho list.

### Bảng chân trị rút gọn

Xét `@Size(min=2,max=4)`:

| Giá trị | @Size | @NotNull | @NotEmpty (nếu áp dụng) |
| --- | --- | --- | --- |
| `null` | Đạt | Không đạt | Không đạt |
| `""` hoặc list rỗng | Không đạt | Đạt | Không đạt |
| `"A"` hoặc list 1 phần tử | Không đạt | Đạt | Đạt |
| `"AB"` hoặc list 2 phần tử | Đạt | Đạt | Đạt |
| `"ABCD"` hoặc list 4 phần tử | Đạt | Đạt | Đạt |
| `"ABCDE"` hoặc list 5 phần tử | Không đạt | Đạt | Đạt |

**Không có annotation nào ở bảng trên tự động cắt ngắn, loại bỏ phần tử hoặc đổi null thành chuỗi rỗng.** Validation là kiểm tra và báo vi phạm; biến đổi dữ liệu thuộc trách nhiệm khác.

## 8. Chương trình Java 17 chạy độc lập: String, List, byte[] và Map

Ví dụ dùng **Java 17**, **Jakarta Bean Validation 3.0** và **Hibernate Validator 8.0.6.Final**. Hibernate Validator là implementation thực thi API. Để chạy ngoài ứng dụng Spring cần cả provider và một implementation của Jakarta Expression Language phục vụ message interpolation.

Cấu trúc dự án Maven:

~~~text
size-constraint-demo/
├── pom.xml
└── src/
    ├── main/java/demo/SizeDemo.java
    └── test/java/demo/SizeDemoTest.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>size-constraint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/SizeDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class SizeDemo {

    static final class Form {
        @Size(min = 3, max = 5,
              message = "nickname length must be 3..5")
        private final String nickname;

        @Size(min = 1, max = 3,
              message = "tags count must be 1..3")
        private final List<
            @NotBlank(message = "tag cannot be blank") String> tags;

        @Size(min = 2, max = 4,
              message = "payload length must be 2..4")
        private final byte[] payload;

        @Size(min = 1, max = 2,
              message = "attributes must contain 1..2 entries")
        private final Map<String, String> attributes;

        Form(String nickname, List<String> tags,
             byte[] payload, Map<String, String> attributes) {
            this.nickname = nickname;
            this.tags = tags;
            this.payload = payload;
            this.attributes = attributes;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Form invalid = new Form(
                "ab", List.of("", "ok", "news", "tools"),
                new byte[]{1}, Map.of());

            Set<ConstraintViolation<Form>> errors =
                validator.validate(invalid);

            System.out.println("invalid=" + errors.size());

            // Set không bảo đảm thứ tự.
            // Chỉ in message đã chọn để output không lệ thuộc
            // cách provider biểu diễn container element path.
            errors.stream()
                .map(ConstraintViolation::getMessage)
                .sorted()
                .forEach(System.out::println);

            Form valid = new Form(
                "Anna", List.of("java", "api"),
                new byte[]{1, 2}, Map.of("theme", "dark"));

            System.out.println(
                "valid=" + validator.validate(valid).size());

            // @Size mặc định cho phép null ở cả bốn field.
            Form allNull = new Form(null, null, null, null);
            System.out.println(
                "allNull=" + validator.validate(allNull).size());

            System.out.println("emojiLength=" + "🙂".length());
        }
    }
}
~~~

Chạy với Maven và JDK 17+ từ thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SizeDemo
~~~

**Stdout của chương trình** (không tính log riêng của provider/Maven):

~~~text
invalid=5
attributes must contain 1..2 entries
nickname length must be 3..5
payload length must be 2..4
tag cannot be blank
tags count must be 1..3
valid=0
allNull=0
emojiLength=2
~~~

### Giải thích năm vi phạm

1. `nickname="ab"` có độ dài 2, nhỏ hơn `min=3` → vi phạm `@Size` trên String.
2. `tags` chứa bốn phần tử, lớn hơn `max=3` → vi phạm `@Size` trên List.
3. Phần tử đầu tiên của `tags` là `""` → vi phạm `@NotBlank` trên phần tử String. Đây là một violation **độc lập** với số lượng tag.
4. `payload` chỉ có một byte, nhỏ hơn `min=2` → vi phạm `@Size` trên mảng primitive.
5. `attributes=Map.of()` có zero entry, nhỏ hơn `min=1` → vi phạm `@Size` trên Map.

Đối tượng `valid` nằm trong các biên của từng ràng buộc và các tag đều không trắng nên không có lỗi. `allNull` cũng không có vi phạm vì ví dụ **cố tình chỉ dùng `@Size` ở cấp field**, còn `@NotBlank` trên phần tử tag không chạy khi toàn bộ List là null. Nếu null là dữ liệu sai nghiệp vụ, hãy thêm `@NotNull` hoặc `@NotEmpty` ở đúng field.

Đoạn chương trình không dùng Spring MVC; nó kiểm tra trực tiếp hợp đồng Bean Validation. Khi Spring tích hợp provider tương thích và kích hoạt validation, ý nghĩa `@Size` giữ nguyên.

## 9. Kiểm thử với JUnit: biên, null và nhiều constraint cùng lúc

Thêm `src/test/java/demo/SizeDemoTest.java` vào dự án ở mục 8:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SizeDemoTest {

    @Test
    void allFourKindsAreChecked() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new SizeDemo.Form(
                "ab",
                List.of("", "ok", "news", "tools"),
                new byte[]{1},
                Map.of());

            var violations = validator.validate(form);

            assertEquals(5, violations.size());

            Set<String> messages = violations.stream()
                .map(ConstraintViolation::getMessage)
                .collect(Collectors.toSet());

            assertEquals(Set.of(
                "nickname length must be 3..5",
                "tags count must be 1..3",
                "tag cannot be blank",
                "payload length must be 2..4",
                "attributes must contain 1..2 entries"
            ), messages);
        }
    }

    @Test
    void exactBoundarySizesAreInclusive() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            var minimum = new SizeDemo.Form(
                "Ann", List.of("ok"),
                new byte[]{1, 2}, Map.of("x", "1"));

            var maximum = new SizeDemo.Form(
                "Annie", List.of("a", "b", "c"),
                new byte[]{1, 2, 3, 4},
                Map.of("x", "1", "y", "2"));

            assertTrue(validator.validate(minimum).isEmpty());
            assertTrue(validator.validate(maximum).isEmpty());
        }
    }

    @Test
    void nullDoesNotViolateSizeAlone() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new SizeDemo.Form(null, null, null, null);

            assertTrue(validator.validate(form).isEmpty());
        }
    }

    @Test
    void elementConstraintIsSeparateFromListSize() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            var form = new SizeDemo.Form(
                "Anna", List.of("", "ok"),
                new byte[]{1, 2}, Map.of("a", "b"));

            var violations = validator.validate(form);
            assertEquals(1, violations.size());
            assertEquals(
                "tag cannot be blank",
                violations.iterator().next().getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Với Maven, dependency và JDK như trên, kết quả mong đợi là **4 test thành công, 0 thất bại**. Các test kiểm tra không chỉ “có lỗi” mà còn kiểm tra mọi loại giá trị, hai điểm biên, `null`, và sự khác biệt giữa độ lớn của List với constraint trên phần tử.

Nếu test chạy trong một dự án Boot đã có provider, nên dùng dependency management của Boot và starter `spring-boot-starter-validation` thay vì thêm một phiên bản provider độc lập không cần thiết.

## 10. ConstraintViolation, thông báo lỗi và trường lỗi

Khi `@Size` không đạt, provider tạo một `ConstraintViolation<T>`. Những thông tin hữu ích:

~~~java
for (ConstraintViolation<SizeDemo.Form> v : errors) {
    String path = v.getPropertyPath().toString();
    String message = v.getMessage();
    Object min = v.getConstraintDescriptor()
                  .getAttributes().get("min");
    Object max = v.getConstraintDescriptor()
                  .getAttributes().get("max");

    System.out.println(path + ": " + message
        + " (min=" + min + ", max=" + max + ")");
}
~~~

Đây là **đoạn minh họa** dùng biến `errors` có được từ `validator.validate(invalid)` ở ví dụ trước. `getPropertyPath()` cho biết trường nào sai; `getMessage()` là thông báo đã nội suy; descriptor chứa tham số ràng buộc như `min/max`.

Thông điệp mặc định có thể dùng template:

~~~text
{jakarta.validation.constraints.Size.message}
~~~

Tùy `MessageInterpolator`/locale của provider, nó trở thành một thông báo hiển thị, thường có hai biên độ dài. Có thể viết message riêng với placeholders:

~~~java
@Size(min = 2, max = 5,
      message = "Số phần tử phải từ {min} đến {max}")
private List<String> choices;
~~~

Khi không hợp lệ, thông điệp được nội suy thành “Số phần tử phải từ 2 đến 5”. Nếu xây API công khai, nên có thêm mã lỗi ổn định (ví dụ `SIZE_OUT_OF_RANGE`), vì chuỗi message có thể đổi theo locale. Cần chú ý:

- `Set<ConstraintViolation<?>>` không cam kết thứ tự: sort theo property path/code khi cần output ổn định.
- Một field có thể có nhiều vi phạm (`@Size` + `@NotBlank`, hoặc constraint trên các phần tử).
- `getInvalidValue()` có thể chứa dữ liệu nhạy cảm; tránh trả thẳng lên response.
- `@Size` trên chính List/Map tạo path tới property, còn lỗi trên phần tử có thể tạo path kèm index/key và node container element.
- Với `@Size` ở cấp field, String/map/array có thể có cả lỗi `@NotNull` nếu ghép nhiều annotation.

Khi thực thi trực tiếp `validator.validate(bean)`, kết quả là **Set**, không tự ném `ConstraintViolationException` chỉ vì dữ liệu không hợp lệ. Ứng dụng quyết định chặn, trả lỗi hoặc chủ động ném exception theo hợp đồng tầng gọi.

## 11. Dùng @Size trong Spring MVC và Spring Boot

Spring Framework tích hợp Jakarta Bean Validation qua `LocalValidatorFactoryBean` và các cơ chế binding/validation. Trong Spring Boot 3, thường dùng dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đây là **đoạn dependency** bổ sung vào dự án Spring Boot có quản lý version từ parent/BOM. Với một dự án Spring Framework thuần, cần cấu hình Bean Validation provider và các integration liên quan.

Một request DTO:

~~~java
package demo.web;

import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

public class CreateGroupRequest {

    @NotBlank
    @Size(min = 3, max = 40)
    private String groupName;

    @NotEmpty
    @Size(max = 5)
    private List<@NotBlank String> members;

    @Size(max = 8)
    private Map<@NotBlank String, String> settings;

    // Cần getters/setters hoặc cơ chế binding thích hợp.
}
~~~

Đây là **DTO minh họa cho web**, chưa độc lập vì thiếu getters/setters và controller. `@Size(max=5)` giới hạn 5 member, `@NotBlank` đảm bảo mỗi member không trắng; `@Size(max=8)` giới hạn số entry của settings, không giới hạn ký tự trong từng value.

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GroupController {

    @PostMapping("/groups")
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateGroupRequest request) {
        // Chạy nghiệp vụ khi request đã qua validation.
        return ResponseEntity.noContent().build();
    }
}
~~~

Đoạn này là **một phần ứng dụng Spring MVC**. `@Valid` yêu cầu validate bean sau khi deserialize `@RequestBody`, nếu có Bean Validation provider hoạt động. Lỗi thông thường của đối tượng request có thể xuất hiện dưới dạng `MethodArgumentNotValidException` (khi không có `BindingResult` ngay sau đối số và không có method-level validation thay đổi luồng). Ứng dụng có thể dùng `@RestControllerAdvice` để trả danh sách field errors.

Với form `@ModelAttribute`, `@Valid` cũng có thể kích hoạt validation; lỗi có thể lấy từ `BindingResult`. Không ép cast `FieldError` của Spring thành `ConstraintViolation`. Đây là hai biểu diễn lỗi khác nhau.

### 11.1. @Size đặt trực tiếp trên request parameter

~~~java
@GetMapping("/search")
public String search(
        @RequestParam
        @Size(min = 2, max = 30) String q) {
    return "Search: " + q;
}
~~~

Đây là đoạn controller minh họa; cần import `GetMapping`, `RequestParam` và `Size` cùng lớp/controller. Với Spring MVC 6.1+ có tích hợp built-in method validation, constraint đặt trực tiếp ở tham số có thể tạo `HandlerMethodValidationException` khi giá trị vi phạm. Luồng cụ thể phụ thuộc cấu hình method validation, proxy và phiên bản Spring.

Phân biệt `@RequestParam String q` **không có giá trị** với `q=""`: Spring có quy tắc required/binding cho tham số trước khi Bean Validation chạy; thông báo “parameter missing” có thể khác lỗi `@Size`.

### 11.2. @Size trên Collection trong JSON khác kích thước JSON

Với request:

~~~json
{
  "members": ["An", "Binh", "Chi", "Dung", "Hoa", "Lan"]
}
~~~

DTO có `@Size(max=5) List<String> members` sẽ không đạt vì List sau deserialize có **6 phần tử**. Nhưng `@Size` không tự giới hạn số byte của HTTP body trước parse. Muốn chống request quá lớn, hãy giới hạn kích thước request và cấu hình parser ở tầng HTTP/Jackson/gateway. Validation sau khi bind không thay thế kiểm soát tài nguyên đầu vào.

Dữ liệu JSON có key trùng có thể bị parser xử lý/ghi đè tùy cấu hình; khi Map đã được tạo, `@Size` chỉ biết số entry thực tế của Map. Nếu cần phát hiện duplicate JSON keys, hãy cấu hình parser tương ứng.

## 12. @Size trên phần tử lồng nhau và sự khác biệt với @Valid

### 12.1. Collection element constraint

~~~java
@Size(min = 1, max = 5)
private List<@Size(min = 2, max = 20) String> labels;
~~~

- `@Size` bên ngoài: 1–5 nhãn.
- `@Size` bên trong: mỗi nhãn từ 2 đến 20 đơn vị độ dài Java.
- Nếu một nhãn `null`, `@Size` bên trong vẫn chấp nhận null; thêm `@NotNull` hoặc `@NotBlank` lên phần tử nếu không cho phép.
- Một list 6 phần tử, trong đó có nhãn dài 1, có thể tạo cả lỗi list size và lỗi element size.

### 12.2. Validation bên trong bean con

~~~java
record Item(
    @NotBlank @Size(max = 30) String sku,
    @Size(min = 1, max = 10) List<String> labels
) {}

record Basket(
    @Size(min = 1, max = 10)
    List<@Valid Item> items
) {}
~~~

Đây là **đoạn minh họa** cần import `List`, `jakarta.validation.Valid`, `NotBlank` và `Size`. `@Size` ngoài List giới hạn số item; `@Valid` yêu cầu validate từng `Item`, trong đó có constraint trên `sku` và `labels`.

Nếu chỉ có `List<Item> items` và `@Size` bên ngoài mà thiếu `@Valid` tại vị trí cần cascade, không nên kỳ vọng Bean Validation kiểm tra mọi field của `Item` tự động.

### 12.3. Map key và value

~~~java
@Size(max = 3)
private Map<
    @NotBlank String,
    @Size(max = 40) String> translatedLabels;
~~~

`@Size(max=3)` giới hạn số entry, `@NotBlank` trên key kiểm tra key String, còn `@Size(max=40)` trên mỗi value kiểm tra riêng độ dài value. Nếu value null cần bị từ chối, thêm `@NotNull` lên value; `@Size` một mình cho phép null.

Đừng ghép các lỗi trên entry thành “Map quá dài”; mỗi constraint có phạm vi và path riêng. Khi hiển thị lỗi, nên giữ cả path và mã lỗi.

## 13. Những giới hạn mà @Size không bao phủ

### 13.1. Không giới hạn độ lớn số nguyên hoặc số thập phân

~~~java
@Min(1)
@Max(100)
private int quantity;
~~~

`@Size(min=1,max=100) int quantity` không phải cách dùng hợp lệ theo chuẩn cho kiểu số. Provider có thể không tìm được validator thích hợp và báo `UnexpectedTypeException` / `ValidationException`. Nếu đầu vào là **chuỗi chữ số** và yêu cầu đúng 6 ký tự, dùng `@Size(min=6,max=6)` (và constraint về ký tự số nếu cần), nhưng số học vẫn nên kiểm tra bằng các ràng buộc số tương ứng.

### 13.2. Không bảo đảm dữ liệu độc nhất hoặc nội dung hợp lệ

`@Size(max=10) List<String> emails` không đảm bảo 10 email hợp lệ, không trùng nhau hoặc có quyền truy cập. Dùng constraint phần tử như `@Email`, kiểm tra duplicate/quan hệ nghiệp vụ riêng. `Set` đã loại phần tử trùng theo `equals/hashCode` nhưng điều đó không có nghĩa dữ liệu đầu vào trước khi tạo Set không có duplicate.

`@Size(max=5) Map<String,Object> settings` cũng không đảm bảo key được phép, value có schema đúng hoặc không có key nguy hiểm. Những yêu cầu đó cần schema validation/domain validation và xử lý JSON phù hợp.

### 13.3. Không thay thế giới hạn byte hoặc cơ sở dữ liệu

`@Size(max=255) String title` giới hạn `String.length()` theo Java, không trực tiếp giới hạn số byte UTF-8. Một số ký tự có thể chiếm nhiều byte. Nếu lưu database column có giới hạn byte hoặc gửi qua hệ thống có quota byte, phải kiểm tra trên độ đo thực tế.

`@Column(length = 255)` của JPA/Hibernate mô tả schema/column mapping, không phải mặc định một Bean Validation constraint được thực thi trên mọi đường xử lý. Một số integration ORM có thể suy ra giới hạn DDL từ metadata `@Size` tùy cấu hình/provider; không dựa vào hành vi đó như bảo đảm đa hệ quản trị. Hãy quản lý schema, request validation và giới hạn storage riêng.

### 13.4. Không tự xác định thứ tự lỗi

Nếu kết hợp `@NotBlank` và `@Size(min=3)`, một String rỗng có thể gây nhiều violation. `Set<ConstraintViolation<T>>` không cam kết thứ tự trả. UI có thể cần chọn ưu tiên hiển thị “bắt buộc nhập” trước “quá ngắn”, nhưng thứ tự phải do tầng trình bày/quy tắc nghiệp vụ quyết định, không suy từ vòng lặp `Set`. Provider có thể có fail-fast hoặc group sequence ảnh hưởng số lỗi được quan sát.

## 14. Message, group và các tham số nâng cao

Khai báo đầy đủ một constraint:

~~~java
@Size(
    min = 2,
    max = 12,
    message = "Phải có từ {min} đến {max} ký tự",
    groups = RegistrationChecks.class
)
private String registrationCode;
~~~

Đây là **đoạn minh họa**; cần khai báo interface `RegistrationChecks` và import `Size`. `groups` xác định đợt validation nào kiểm tra constraint. Nếu gọi `validator.validate(bean)` mặc định, thường chỉ nhóm `Default` được xét, không tự gồm mọi group tùy biến. Khi cần:

~~~java
Set<ConstraintViolation<Form>> errors =
    validator.validate(form, RegistrationChecks.class);
~~~

Đây là đoạn minh họa cần `Form`, `RegistrationChecks` và biến `validator` tồn tại. Khi dùng `@Validated(RegistrationChecks.class)` trong Spring, có thể chọn nhóm validation áp dụng tại một boundary, nhưng cần xem ngữ cảnh Spring MVC/method validation để tránh nhầm.

Các thuộc tính khác:

- `message`: template thông báo lỗi, có thể chứa `{min}` và `{max}`.
- `groups`: nhóm kiểm tra; mặc định là `Default`.
- `payload`: metadata mở rộng, không dùng để thay thế quy tắc đếm.
- `@Size.List` hoặc khai báo `@Size` lặp lại: phục vụ nhiều ràng buộc `@Size` trên cùng vị trí (thường phân biệt group). Tránh đặt hai biên mâu thuẫn nếu chưa có mục đích rõ.

Nếu muốn nhiều quy tắc theo các giai đoạn, hãy định nghĩa group theo nghiệp vụ và test đường gọi thật; `@Size` không tự biết “màn hình tạo mới” khác “màn hình sửa” nếu không cấu hình nhóm/boundary.

## 15. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| `@Size(min=1)` được cho là từ chối null | Theo chuẩn, `@Size` cho phép null. | Thêm `@NotNull`, `@NotEmpty` hoặc `@NotBlank` nếu dữ liệu bắt buộc. |
| Dùng `@Size(max=5)` trên List để giới hạn độ dài từng phần tử | Chỉ giới hạn `List.size()`. | Thêm `List<@Size(max=5) String>` cho phần tử. |
| Dùng `@Size(max=10)` trên Map để giới hạn key | Chỉ đếm entry. | Dùng `Map<@Size(max=10) String, ...>` cho key. |
| Dùng `@Size(min=2)` rồi nghĩ chuỗi toàn dấu cách không hợp lệ | `length()` vẫn đếm khoảng trắng. | Kết hợp `@NotBlank` và chính sách normalize nếu phù hợp. |
| Tưởng emoji luôn bằng một ký tự cho `@Size` | String Java đếm UTF-16 code units. | Chọn tiêu chí code point/grapheme riêng nếu nghiệp vụ yêu cầu. |
| Dùng `@Size` trên `int`/`BigDecimal` | Không phải kiểu chuẩn được hỗ trợ. | Dùng `@Min`/`@Max`/`@Digits` hoặc ràng buộc số khác. |
| Đếm số key đầu vào JSON trước khi tạo Map | Map đã được parser xây dựng và có thể ghi đè key trùng. | Giới hạn/kiểm tra parser và schema ở biên input. |
| Chỉ đặt `@Size` trên mảng List bean mà không có `@Valid` | Giới hạn số phần tử, không cascade kiểm tra bean con. | Thêm `List<@Valid Child>` tại điểm cần kiểm tra lồng nhau. |
| Nghĩ `@Size(max=255)` bảo đảm <=255 byte UTF-8 | Java length và byte length khác nhau. | Xác định và kiểm tra giới hạn byte riêng. |
| Chỉ import `jakarta.validation-api` rồi mong validation tự chạy | Cần provider và điểm kích hoạt validation. | Thêm provider/starter và `Validator.validate` hoặc `@Valid` ở boundary. |
| Trả raw violation/invalidValue thẳng cho client | Có thể lộ dữ liệu hoặc metadata nội bộ. | Ánh xạ thành field/code/message an toàn, sort nếu cần. |
| Áp dụng `@Size` cho lớp chỉ triển khai `Iterable` | Chuẩn chỉ bảo đảm `Collection`, không phải mọi Iterable. | Dùng Collection hoặc custom constraint nếu cần. |
| Gắn `@Size` với tham số min âm, max nhỏ hơn min | Metadata ràng buộc vô lý. | Kiểm tra quy tắc biên trong code review và test. |
| Tưởng `@Size` luôn tự chạy với mọi request | Annotation cần Bean Validation được kích hoạt và tích hợp đúng. | Test thực tế controller/binder/service với provider. |

## 16. Checklist thiết kế và kiểm thử

1. Xác định **kiểu dữ liệu thật** của property: `CharSequence`, array, `Collection` hay `Map`.
2. Viết rõ đơn vị kích thước: Java UTF-16 length, số phần tử, hay số entry.
3. Chọn `min/max` đúng nghiệp vụ; kiểm tra hai giá trị biên **đều hợp lệ**.
4. Xác định `null` có được phép hay không; bổ sung `@NotNull`/`@NotEmpty`/`@NotBlank` khi bắt buộc.
5. Với String, xác định có trim/normalize và có cần giới hạn grapheme/code point/byte không.
6. Với collection, phân biệt kiểm tra **số phần tử** và **ràng buộc từng phần tử**.
7. Với Map, phân biệt **số entry** và kiểm tra key/value.
8. Với mảng, lưu ý `@Size` không kiểm tra nội dung từng phần tử.
9. Bật provider phù hợp với namespace `jakarta.validation`; kiểm tra điểm thực thi (`@Valid`, `@Validated` hoặc `Validator`).
10. Viết test cho null, rỗng, min−1, min, max, max+1, dữ liệu có Unicode, List chứa phần tử lỗi, Map có key/value lỗi.
11. Chuyển `ConstraintViolation`/`BindingResult` thành danh sách lỗi rõ field, code, message; không tiết lộ giá trị nhạy cảm.
12. Nếu cần bảo vệ tài nguyên hệ thống, bổ sung giới hạn kích thước HTTP body, JSON parser, database và storage tương ứng.

**Tự kiểm tra kiến thức**

1. `@Size(min=2,max=4)` có chấp nhận String `null` không?
2. List gồm ba phần tử `null` có vượt qua `@Size(min=3,max=3)` không?
3. `@Size(max=2) Map<String,String>` kiểm tra số key, tổng ký tự value hay số entry?
4. `"   "` có đạt `@Size(min=3,max=3)` không? Có đạt `@NotBlank` không?
5. Một `List<@Size(min=2) String>` có bị giới hạn số phần tử không?
6. `@Size(max=1)` trên String chứa một emoji “🙂” có luôn đạt không?
7. Nếu muốn danh sách không null, có 1–5 phần tử và mỗi phần tử không trắng, viết các constraint ở đâu?

**Đáp án:** (1) Có, null hợp lệ theo `@Size`; (2) Có nếu List thực sự chứa ba phần tử; (3) số entry; (4) đạt `@Size`, không đạt `@NotBlank`; (5) không, chỉ kiểm tra kích thước từng String; (6) không, “🙂” có `String.length()==2`; (7) `@NotEmpty @Size(max=5) List<@NotBlank String>`.

## 17. Tài liệu tham khảo

- Jakarta Bean Validation 3.0 Specification, phần *`@Size` constraint*: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API, `Size`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/Size.html
- Jakarta Bean Validation 3.0 API, `NotEmpty`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotEmpty.html
- Hibernate Validator 8, *Reference Guide*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Hibernate Validator 8.0 series và phiên bản ví dụ: https://hibernate.org/validator/releases/8.0/
- Spring Framework, *Java Bean Validation*: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework, *Spring MVC Validation*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
