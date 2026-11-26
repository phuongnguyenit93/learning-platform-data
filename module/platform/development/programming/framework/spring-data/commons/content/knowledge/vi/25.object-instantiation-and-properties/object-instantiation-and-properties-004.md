# Tên tham số, @ConstructorProperties và tùy chọn -parameters

Một constructor có đủ kiểu tham số chưa chắc đã đủ thông tin để Spring Data khởi tạo đối tượng. Nếu hai tham số cùng có kiểu `String`, hạ tầng không thể chỉ nhìn kiểu để biết giá trị nào dành cho `sku`, giá trị nào dành cho `displayName`. Khi cơ chế mapping gắn đối số constructor với thuộc tính theo tên, tên tham số là một phần của hợp đồng ánh xạ.

Bài học thuộc chương **Khởi tạo và gán thuộc tính** của **Spring Data Commons**. Trọng tâm là thông tin tên tham số trong lớp Java, cách cung cấp tên bằng `@ConstructorProperties`, và cách giữ tên bằng tùy chọn biên dịch `-parameters`. Các nguyên tắc này giúp đọc đúng hành vi tạo đối tượng của Spring Data, nhưng không thay thế quy tắc riêng của JPA, JDBC, MongoDB hoặc những module lưu trữ khác.

## 1. Ba việc khác nhau trong quá trình tạo đối tượng

Để hiểu đúng vai trò của tên tham số, tách quá trình materialization, tức biến dữ liệu đã đọc thành đối tượng Java, thành ba câu hỏi:

1. **Dùng creator nào?** Hạ tầng chọn constructor hoặc factory method theo quy tắc được hỗ trợ.
2. **Cấp giá trị nào cho từng đối số?** Khi dùng constructor binding theo thuộc tính, hạ tầng cần liên hệ tham số với persistent property tương ứng.
3. **Gán các thuộc tính còn lại ra sao?** Sau khi tạo đối tượng, hạ tầng có thể xử lý những thuộc tính chưa được constructor nhận, tùy mô hình mapping và module.

Tên tham số chủ yếu giải quyết câu hỏi thứ hai. Một constructor đã được chọn đúng vẫn có thể không dùng được nếu hạ tầng không biết đối số của nó đại diện cho thuộc tính nào.

Ngược lại, có tên tham số không giải quyết mọi vấn đề: thuộc tính có thể không tồn tại, kiểu dữ liệu có thể không chuyển đổi được, giá trị có thể vi phạm invariant của domain object, hoặc module lưu trữ có thể dùng một cơ chế tạo đối tượng khác.

## 2. Ví dụ: hai tham số cùng kiểu không thể phân biệt bằng kiểu

Xét một lớp bất biến:

```java
public final class StockItem {

    private final String sku;
    private final String displayName;
    private final int quantity;

    public StockItem(String sku, String displayName, int quantity) {
        this.sku = sku;
        this.displayName = displayName;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public String getDisplayName() {
        return displayName;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

Giả sử lớp này được module phù hợp nhận diện là một đối tượng cần mapping, và dữ liệu logic sau chuyển đổi gồm:

```text
sku         = "BOOK-42"
displayName = "Spring Data căn bản"
quantity    = 8
```

Hạ tầng mong muốn tạo đối tượng tương đương:

```java
new StockItem("BOOK-42", "Spring Data căn bản", 8);
```

Nhìn vào kiểu `(String, String, int)`, hai giá trị đầu vẫn có thể bị hoán đổi mà Java không báo lỗi kiểu. Thông tin cần thiết là quan hệ:

```text
tham số sku         -> thuộc tính sku
tham số displayName -> thuộc tính displayName
tham số quantity    -> thuộc tính quantity
```

Đây là ánh xạ tên thuộc tính, không phải một cam kết rằng cột đầu tiên của kết quả truy vấn luôn là đối số đầu tiên. Việc đọc tên cột, tên field và chuyển đổi dữ liệu thuộc tầng mapping của module lưu trữ.

## 3. Tên trong mã nguồn chưa chắc còn trong class file

Khi viết constructor, lập trình viên nhìn thấy tên `sku`, `displayName` và `quantity`. Tuy nhiên, công cụ đọc thông tin lúc chạy không đọc lại mã nguồn Java. Nó làm việc với lớp đã biên dịch và metadata đi kèm.

Với một lớp Java thông thường không giữ metadata tên tham số, Java reflection có thể cung cấp các tên tổng hợp như:

```text
arg0
arg1
arg2
```

Các tên này không phải tên persistent property của `StockItem`. Không nên đổi tên thuộc tính của domain thành `arg0`, `arg1` để làm mapping chạy được.

Có hai cách chính được xét trong bài:

| Cách cung cấp tên | Thông tin được lưu ở đâu? | Phạm vi tác động |
| --- | --- | --- |
| `javac -parameters` | Metadata tham số trong class file | Những constructor và phương thức được tác vụ biên dịch đó xử lý |
| `@ConstructorProperties` | Annotation trên một constructor | Constructor được annotation mô tả |

Hai cách đều cung cấp thông tin tên, nhưng hoạt động ở những lớp khác nhau. Đặc biệt, có `@ConstructorProperties` không đồng nghĩa `Parameter.isNamePresent()` của Java reflection sẽ trở thành `true`.

## 4. Giữ tên tham số bằng -parameters

`-parameters` là tùy chọn của Java compiler để lưu tên tham số hình thức vào class file. Khi metadata này được giữ lại, Java reflection có thể đọc tên khai báo thay cho tên tổng hợp.

Với lớp `StockItem` ở trên, kết quả mong đợi khi biên dịch có tùy chọn là:

```text
sku         namePresent=true
 displayName namePresent=true
quantity    namePresent=true
```

Khoảng cách trình bày không có ý nghĩa; các tên cần đọc được là `sku`, `displayName` và `quantity`.

### 4.1. Cấu hình Maven

Trong một dự án Maven, có thể cấu hình Maven Compiler Plugin để bật lưu tên tham số:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đoạn trên minh họa phần cấu hình cần ghép vào build hiện có. Phiên bản plugin và Java toolchain vẫn do dự án quản lý; không tạo thêm một cấu hình plugin trùng lặp chỉ để bật thuộc tính này.

Một số parent hoặc convention build đã bật sẵn tùy chọn. Điều cần xác nhận là tác vụ thực sự biên dịch lớp domain có nhận tùy chọn hay không, chứ không chỉ là trong repository có xuất hiện một đoạn XML chứa chữ `parameters`.

### 4.2. Cấu hình Gradle cho mã Java

Với Groovy DSL:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Với Kotlin DSL dùng để cấu hình tác vụ biên dịch Java:

```kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

Việc file build được viết bằng Kotlin DSL không làm cấu hình trên trở thành cấu hình compiler cho mã nguồn Kotlin. Nó vẫn nhắm tới `JavaCompile`.

Các đoạn cấu hình trong bài là ví dụ dành cho dự án học tập. Chúng không có nghĩa phải dùng đồng thời Maven và Gradle.

### 4.3. Bật ở nơi tạo ra lớp, không chỉ ở ứng dụng tiêu thụ lớp

Giả sử domain object nằm trong thư viện `inventory-domain`, còn repository nằm trong ứng dụng `inventory-service`. Bật `-parameters` khi biên dịch `inventory-service` không bổ sung metadata cho một JAR `inventory-domain` đã được biên dịch trước đó.

Tương tự:

- Thêm tùy chọn nhưng tiếp tục chạy class file cũ không làm metadata xuất hiện.
- Cấu hình chỉ dành cho test không bảo đảm lớp production đã giữ tên.
- Biên dịch bằng IDE và biên dịch bằng CI có thể đi qua các cấu hình khác nhau.
- Công cụ xử lý bytecode hoặc đóng gói có thể ảnh hưởng metadata trong artifact cuối cùng.

Đối tượng cần kiểm tra là lớp thực tế mà ứng dụng nạp lúc chạy.

### 4.4. -parameters không đồng nghĩa với thông tin debug

Không coi `-g` hoặc việc IDE hiển thị tên biến khi debug là bằng chứng tương đương với metadata tham số của `-parameters`.

Một số tổ hợp framework và công cụ có thể đọc những nguồn metadata khác, nhưng không nên dựa vào khả năng suy luận từ debug information như một hợp đồng ổn định cho constructor binding. Nếu chọn chiến lược giữ tên tham số Java, hãy cấu hình và kiểm tra chính metadata đó.

## 5. Cung cấp tên bằng @ConstructorProperties

`@ConstructorProperties` là annotation của Java, nằm trong package `java.beans`, không phải annotation của Spring Data:

```java
import java.beans.ConstructorProperties;
```

Annotation mô tả constructor bằng một mảng tên thuộc tính, theo đúng thứ tự các đối số. Một biến thể của lớp ví dụ là:

```java
import java.beans.ConstructorProperties;

public final class StockItem {

    private final String sku;
    private final String displayName;
    private final int quantity;

    @ConstructorProperties({"sku", "displayName", "quantity"})
    public StockItem(String sku, String displayName, int quantity) {
        this.sku = sku;
        this.displayName = displayName;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public String getDisplayName() {
        return displayName;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

Trong cơ chế constructor mapping có hỗ trợ annotation này, danh sách tên cho phép liên hệ:

```text
đối số 0 -> sku
đối số 1 -> displayName
đối số 2 -> quantity
```

Như vậy, annotation có thể cung cấp tên cho việc mapping ngay cả khi tên tham số hình thức không được reflection báo là có mặt trong class file.

### 5.1. Số lượng và thứ tự đều là một phần của hợp đồng

Với constructor có ba tham số, danh sách tên phải mô tả đúng ba tham số theo đúng thứ tự.

Ví dụ sai khi dùng annotation làm nguồn tên:

```java
@ConstructorProperties({"sku", "displayName", "quantity"})
public StockItem(String displayName, String sku, int quantity) {
    this.sku = sku;
    this.displayName = displayName;
    this.quantity = quantity;
}
```

Ở đây, đối số đầu tiên được annotation mô tả là `sku`, nhưng thân constructor lại dùng nó làm `displayName`. Hai đối số đầu cùng kiểu `String`, nên lỗi có thể trở thành dữ liệu bị hoán đổi thay vì lỗi chuyển đổi kiểu rõ ràng.

Annotation đúng cho thứ tự tham số này phải là:

```java
@ConstructorProperties({"displayName", "sku", "quantity"})
```

Điều đó không có nghĩa nên đảo thứ tự constructor tùy tiện. Khi sửa constructor, cần sửa đồng bộ hợp đồng metadata và những nơi gọi nó.

### 5.2. Annotation không tự chọn constructor

`@ConstructorProperties` trả lời câu hỏi “đối số này tương ứng thuộc tính nào?”. Không dùng nó như một thay thế chung cho việc lựa chọn persistence creator.

Nếu một lớp có nhiều constructor và cần chỉ rõ constructor dùng cho persistence, có thể sử dụng `@PersistenceCreator` theo quy tắc của cơ chế mapping đang áp dụng:

```java
import java.beans.ConstructorProperties;

import org.springframework.data.annotation.PersistenceCreator;

public final class StockItem {

    private final String sku;
    private final String displayName;
    private final int quantity;

    public StockItem(String sku) {
        this(sku, sku, 0);
    }

    @PersistenceCreator
    @ConstructorProperties({"sku", "displayName", "quantity"})
    public StockItem(String sku, String displayName, int quantity) {
        this.sku = sku;
        this.displayName = displayName;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public String getDisplayName() {
        return displayName;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

Hai annotation có hai vai trò độc lập:

| Annotation | Vai trò trong ví dụ |
| --- | --- |
| `@PersistenceCreator` | Đánh dấu creator được dùng để tạo đối tượng bởi hạ tầng hỗ trợ nó |
| `@ConstructorProperties` | Cung cấp tên thuộc tính tương ứng với các đối số của constructor |

Một constructor được chọn bằng `@PersistenceCreator` vẫn cần có cách cung cấp tên khi đường binding của nó dựa trên tên. Ngược lại, gắn `@ConstructorProperties` không giải quyết mọi trường hợp mơ hồ giữa các creator.

### 5.3. Không áp dụng annotation này lên static factory method

`@ConstructorProperties` dành cho constructor. Không chuyển nó lên một static factory method rồi kỳ vọng có cùng tác dụng.

Nếu lựa chọn static factory làm persistence creator, cần dùng cơ chế được hỗ trợ để cung cấp metadata cho tham số của factory, chẳng hạn giữ tên tham số Java bằng `-parameters`, cùng quy tắc creator của phiên bản và module đang dùng.

### 5.4. Lưu ý khi dùng Java module system

Trong JDK có module system, `java.beans.ConstructorProperties` thuộc module `java.desktop`. Nếu dự án khai báo một named module và cần dùng annotation này, cấu hình module phải cho phép truy cập package đó; việc khai báo `requires java.desktop;` là cách thông thường trong trường hợp ấy.

Điểm này liên quan đến việc biên dịch và phân phối module Java, không có nghĩa ứng dụng phải có giao diện đồ họa.

## 6. Tên thuộc tính Java khác tên lưu trữ

Giả sử đối tượng có thuộc tính Java:

```java
private final String displayName;
```

nhưng module lưu trữ ánh xạ nó sang tên `display_name` trong bảng hoặc document. Luồng khái niệm là:

```text
Tên lưu trữ display_name
        |
        | mapping và chuyển đổi của module lưu trữ
        v
Persistent property displayName
        |
        | constructor binding theo tên thuộc tính
        v
Đối số constructor displayName
```

Vì vậy, danh sách annotation thông thường vẫn dùng tên thuộc tính Java:

```java
@ConstructorProperties({"sku", "displayName", "quantity"})
```

Không đổi thành `"display_name"` chỉ vì tên cột hoặc field bên ngoài có dấu gạch dưới. Tên trong annotation phải tương ứng với persistent property mà hạ tầng dùng để cấp giá trị, không phải tự động lấy mọi tên vật lý của kho dữ liệu.

Annotation mapping tên lưu trữ lại phụ thuộc module. Ví dụ, annotation `@Field` của Spring Data MongoDB và annotation `@Column` của Spring Data Relational thuộc những hệ mapping khác nhau. Không nhầm chúng với một annotation cùng tên trong JPA và kỳ vọng mọi module diễn giải giống nhau.

Quan hệ này cũng giúp giải thích vì sao đổi tên một field hoặc getter Java có thể làm constructor binding hỏng dù schema bên ngoài chưa đổi. Mapping tên lưu trữ vẫn đúng, nhưng hợp đồng tên thuộc tính và tên đối số đã không còn khớp.

## 7. Tự quan sát metadata bằng Java reflection

Có thể kiểm tra metadata của constructor bằng một đoạn Java nhỏ. Ví dụ sau đọc đúng constructor ba tham số của `StockItem`:

```java
import java.beans.ConstructorProperties;
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;
import java.util.Arrays;

public class ConstructorMetadataExample {

    public static void main(String[] args) throws Exception {
        Constructor<StockItem> constructor = StockItem.class.getDeclaredConstructor(
                String.class,
                String.class,
                int.class
        );

        for (Parameter parameter : constructor.getParameters()) {
            System.out.printf(
                    "%s namePresent=%s%n",
                    parameter.getName(),
                    parameter.isNamePresent()
            );
        }

        ConstructorProperties properties = constructor.getAnnotation(
                ConstructorProperties.class
        );

        System.out.println(
                properties == null
                        ? "ConstructorProperties: absent"
                        : "ConstructorProperties: " + Arrays.toString(properties.value())
        );
    }
}
```

Với lớp Java thông thường và constructor trong ví dụ, có thể đối chiếu:

| Cấu hình hoặc metadata | `Parameter.getName()` | `isNamePresent()` | `@ConstructorProperties` |
| --- | --- | --- | --- |
| Không giữ tên, không annotation | Thường là `arg0`, `arg1`, `arg2` | `false` | Không có |
| Có `-parameters`, không annotation | `sku`, `displayName`, `quantity` | `true` | Không có |
| Không giữ tên, có annotation | Vẫn có thể là `arg0`, `arg1`, `arg2` | `false` | Có danh sách tên thuộc tính |
| Có cả hai, tên nhất quán | Tên tham số đã khai báo | `true` | Có danh sách tên thuộc tính |

Điểm cần quan sát là hai kênh metadata độc lập. Nếu annotation tồn tại nhưng `isNamePresent()` là `false`, không được kết luận annotation đã vô hiệu. Reflection vẫn đọc được annotation; framework có hỗ trợ nó sẽ khai thác nguồn thông tin đó.

Ngược lại, thấy `isNamePresent()` là `true` chỉ chứng minh có tên tham số hình thức, chưa chứng minh các tên đó khớp persistent property. Một constructor có tham số `a`, `b`, `c` được biên dịch với `-parameters` vẫn giữ đúng những tên không có ý nghĩa mapping ấy.

## 8. Những lỗi tên tham số thường gặp

### 8.1. Tên tồn tại nhưng không khớp thuộc tính

```java
public StockItem(String productCode, String label, int amount) {
    this.sku = productCode;
    this.displayName = label;
    this.quantity = amount;
}
```

Bật `-parameters` giữ được `productCode`, `label`, `amount`. Nó không phân tích thân constructor để tự suy ra ba tên này được gán cho `sku`, `displayName`, `quantity`.

Nếu dùng binding theo tên và không có một cơ chế khai báo khác, đây vẫn là một hợp đồng không khớp. Có thể đổi tên tham số cho nhất quán, hoặc cung cấp danh sách `@ConstructorProperties` đúng cho constructor.

### 8.2. Metadata bị mâu thuẫn sau refactor

Nếu lớp có cả tên tham số được giữ lại và `@ConstructorProperties`, hãy giữ chúng nhất quán với thuộc tính. Không thiết kế dựa trên việc framework “chắc sẽ ưu tiên nguồn mình muốn” khi hai nguồn đưa ra tên khác nhau.

Một thao tác đổi tên thuộc tính cần xem ít nhất:

- Field hoặc property thực tế của domain.
- Tham số của creator được dùng cho persistence.
- Chuỗi tên trong `@ConstructorProperties`, nếu có.
- Mapping tên lưu trữ và những hợp đồng projection hoặc truy vấn liên quan.

Các chuỗi trong annotation không phải lúc nào cũng được IDE cập nhật như một tham chiếu Java có kiểu. Kiểm thử khôi phục đối tượng giúp phát hiện những chỗ sót.

### 8.3. Nghĩ rằng tên đúng sẽ giải quyết dữ liệu null

Tên tham số đúng chỉ giúp chọn nguồn giá trị. Nếu `quantity` là primitive `int` nhưng dữ liệu nguồn là `null`, còn cần xét chuyển đổi và chính sách giá trị mặc định của module.

Tương tự, nếu constructor từ chối `quantity < 0`, việc đọc dữ liệu cũ có giá trị âm vẫn có thể thất bại dù tên và kiểu đã được khai báo chính xác. Không chữa lỗi dữ liệu bằng cách sửa annotation tên tham số.

### 8.4. Constructor được sinh nhưng metadata không như mong đợi

Với mã được sinh bởi công cụ hoặc annotation processor, không mặc định rằng một annotation ở mã nguồn sẽ làm constructor sinh ra có đầy đủ mọi metadata mong muốn.

Cần xem constructor thực tế và artifact được biên dịch. Nếu chọn chiến lược `-parameters`, tùy chọn phải áp dụng cho tác vụ tạo class file đó. Nếu chọn `@ConstructorProperties`, phải xác nhận annotation thật sự hiện diện trên constructor cần dùng.

## 9. Record, Kotlin và projection cần được phân biệt

### 9.1. Java record

Java record có record components và canonical constructor tương ứng. Với constructor canonical do `javac` tạo hoặc biên dịch, tên tham số gắn với tên record component; không nên áp dụng máy móc kết luận rằng mọi record thiếu `-parameters` đều sẽ mất tên như một POJO thông thường.

Ví dụ:

```java
public record StockItem(String sku, String displayName, int quantity) {
}
```

Tuy vậy, hạ tầng đang dùng vẫn phải hỗ trợ record và lựa chọn creator phù hợp. Nếu record có thêm constructor hoặc logic validation, cần xét các quy tắc đó thay vì xem record là cách bỏ qua mọi vấn đề mapping.

### 9.2. Mã nguồn Kotlin

Kotlin có metadata và cơ chế hỗ trợ riêng trong Spring Data. Tùy chọn `-parameters` của Java compiler không thay thế toàn bộ cấu hình compiler Kotlin hoặc các dependency cần cho hỗ trợ Kotlin của framework.

Khi một ứng dụng trộn Java và Kotlin, xác định ngôn ngữ nào tạo ra lớp domain và framework đang đọc nguồn metadata nào. Không suy luận từ kết quả của một POJO Java sang mọi data class Kotlin.

### 9.3. Class-based projection và DTO

Tên tham số constructor cũng có thể liên quan đến việc tạo DTO hoặc xác định thuộc tính cần lấy cho class-based projection. Nhưng đường tạo DTO còn phụ thuộc kiểu truy vấn và module: derived query, JPQL constructor expression, native query và document mapping không có cùng một hợp đồng chung.

Bật `-parameters` không tự sửa tên alias, thứ tự đối số của một constructor expression hoặc một result mapping sai. Trước hết xác định API nào đang tạo DTO và nó yêu cầu ánh xạ theo tên hay theo vị trí.

## 10. Phạm vi của Commons và giới hạn theo store

Các ví dụ trong bài mô tả nguyên tắc của cơ chế mapping hỗ trợ constructor binding trong hệ Spring Data. Không nên dùng chúng để khẳng định mọi repository đều tạo entity bằng cùng một pipeline.

| Ngữ cảnh | Cách đọc đúng vai trò của tên tham số |
| --- | --- |
| Store dùng cơ chế mapping hỗ trợ persistence creator của Spring Data | Tên tham số hoặc metadata constructor có thể là đầu vào trực tiếp cho binding |
| Entity được JPA provider tạo và quản lý | Phải tuân theo quy tắc entity và cơ chế instantiation của JPA provider; không coi `@ConstructorProperties` là cách thay thế mọi yêu cầu của JPA |
| Class-based projection hoặc DTO từ truy vấn | Kiểm tra hợp đồng cụ thể của API truy vấn và module |
| Fragment tự viết gọi `new StockItem(...)` | Chính mã ứng dụng cấp đối số; reflection metadata không tự thay đổi thứ tự đối số đã viết |

Ví dụ, một repository fragment gọi trực tiếp:

```java
return new StockItem(sku, displayName, quantity);
```

thì Java truyền đối số theo lời gọi đã viết. `@ConstructorProperties` không can thiệp vào phép gọi `new` này để tự đảo lại đối số.

Cũng không nhầm tên tham số constructor của domain object với tên tham số phương thức repository. `@Param` dùng trong một số cơ chế truy vấn không phải annotation đặt lên constructor để giải quyết quá trình materialization đang xét.

## 11. Chọn chiến lược và kiểm chứng ở đúng mức

Với mã Java do dự án kiểm soát, giữ tên tham số bằng `-parameters` thường thuận tiện vì hợp đồng tên nằm ngay ở khai báo constructor. Khi cần cung cấp tên rõ ràng cho một constructor, `@ConstructorProperties` là một lựa chọn được cơ chế mapping hỗ trợ khai thác.

Không nhất thiết phải dùng đồng thời cả hai trên mọi lớp. Điều cần bảo đảm là creator được chọn có nguồn metadata hợp lệ, nhất quán với persistent property và còn tồn tại trong artifact được triển khai.

Có hai mức kiểm chứng bổ sung cho nhau:

1. **Kiểm tra metadata lớp:** reflection cho biết tên tham số có được giữ và annotation có tồn tại không.
2. **Kiểm tra mapping thực tế:** đọc dữ liệu qua converter hoặc repository của module đang dùng và xác nhận object được khôi phục đúng.

Mức thứ nhất không chứng minh toàn bộ mapping đã đúng. Mức thứ hai giúp phát hiện tên thuộc tính sai, cấu hình store sai, chuyển đổi sai hoặc constructor không phải creator được chọn.

Một tình huống kiểm thử có ý nghĩa dùng hai chuỗi khác nhau:

```text
sku         = "SKU-ALPHA"
displayName = "Tên hiển thị BETA"
quantity    = 7
```

Sau khi đọc đối tượng qua đường mapping thực tế, cần xác nhận:

```java
assertEquals("SKU-ALPHA", item.getSku());
assertEquals("Tên hiển thị BETA", item.getDisplayName());
assertEquals(7, item.getQuantity());
```

Đây là ý tưởng assertion dùng với framework kiểm thử của dự án. Nếu hai giá trị chuỗi giống hệt nhau, một lỗi hoán đổi đối số sẽ khó bị phát hiện. Nếu chỉ gọi `new StockItem(...)`, phép thử chưa xác nhận được constructor binding của framework.

## 12. Chẩn đoán khi không tạo được đối tượng

Đi theo chuỗi câu hỏi sau:

1. **Ai đang tạo đối tượng?** Commons mapping, một converter của store, JPA provider, cơ chế DTO của truy vấn hay mã `new` trong fragment?
2. **Creator nào được chọn?** Có đang dùng constructor dự kiến không? Có cần chỉ rõ bằng cơ chế creator được hỗ trợ không?
3. **Tên được lấy từ đâu?** Metadata `-parameters`, `@ConstructorProperties`, record metadata hay cơ chế ngôn ngữ khác?
4. **Tên có khớp persistent property không?** Phân biệt `displayName` với tên lưu trữ `display_name` và với một tên tham số như `label`.
5. **Số lượng và thứ tự có đúng không?** Đặc biệt lưu ý các tham số cùng kiểu có thể bị gán nhầm mà không lỗi kiểu.
6. **Artifact có đúng không?** Lớp đang chạy có phải lớp vừa được biên dịch với cấu hình mong muốn không?
7. **Giá trị và kiểu có hợp lệ không?** Sau khi giải quyết metadata, vẫn phải xét null, conversion và invariant trong constructor.

Thông báo lỗi cụ thể có thể khác theo phiên bản và module. Không cần chờ đúng một chuỗi lỗi cố định mới kiểm tra metadata; quan sát trực tiếp creator và lớp được nạp thường giúp khoanh vùng rõ hơn.

## 13. Bài tập thực hành

Trong một dự án dùng module hỗ trợ constructor mapping:

1. Tạo lớp bất biến `StockItem` với hai thuộc tính `String` và một thuộc tính `int` như ví dụ.
2. Quan sát metadata của constructor trong một biến thể không giữ tên và không có `@ConstructorProperties`.
3. Bật giữ tên tham số cho đúng module biên dịch lớp, tạo lại artifact và đối chiếu `getName()` cùng `isNamePresent()`.
4. Tạo một biến thể chỉ dùng `@ConstructorProperties`; xác nhận annotation cung cấp danh sách tên ngay cả khi reflection không báo có tên tham số hình thức.
5. Đổi thứ tự hai tham số `String` nhưng giữ annotation cũ, rồi dùng dữ liệu khác nhau để nhận diện lỗi binding; sau đó sửa metadata cho nhất quán.
6. Nếu store có tên lưu trữ `display_name`, giữ tên thuộc tính logic `displayName` trong hợp đồng constructor và kiểm tra cả vòng đọc dữ liệu.

Kết quả cần đạt là phân biệt được **lựa chọn creator**, **cung cấp tên tham số**, và **mapping giá trị của store**. `-parameters` và `@ConstructorProperties` giải quyết phần thông tin tên; tính đúng đắn của đối tượng cuối cùng còn phụ thuộc hợp đồng domain và đường tạo đối tượng thực tế.
