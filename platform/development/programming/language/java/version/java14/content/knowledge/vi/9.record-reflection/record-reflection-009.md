# Kiểm tra thư viện ánh xạ dữ liệu hỗ trợ record chính thức

## Mục tiêu

Java `record` có cấu trúc rõ ràng và có API **reflection** chuẩn, nhưng điều đó **không đồng nghĩa mọi thư viện ánh xạ dữ liệu (data mapping)** tự động hiểu cách tạo một đối tượng `record`. Khi chuyển JSON, hàng SQL hoặc một DTO sang `record`, thư viện phải có khả năng đọc **record components**, xác định **canonical constructor**, liên kết tên/kiểu dữ liệu với đúng tham số và xây dựng đối tượng mà không dựa vào setter của JavaBean.

Sau bài này, bạn sẽ:

- Phân biệt **JDK có thể phản chiếu record** với **thư viện bên ngoài tuyên bố hỗ trợ record chính thức**.
- Kiểm tra đúng phiên bản JDK và phiên bản thư viện **thực sự được giải quyết trong build**, thay vì chỉ nhìn tên dependency trong source.
- Đọc tài liệu nhà phát triển, release notes và phạm vi hỗ trợ của thư viện (JSON, mapper DTO, JDBC, ORM).
- Tự viết **compatibility smoke test** chứng minh serialize/deserialze, khởi tạo qua canonical constructor, mapping danh sách, validation và trường hợp lỗi.
- Nhận diện những bẫy về tên component, annotations, null, generic type, nested records, Java Platform Module System (JPMS) và native image.
- Đưa ra quyết định triển khai có kiểm chứng: tiếp tục dùng thư viện, nâng cấp, thêm adapter tùy biến hoặc thay đổi loại dữ liệu đích.

**Ngữ cảnh phiên bản:** `record` xuất hiện dưới dạng preview trong Java 14 và trở thành tính năng **chính thức từ Java 16** ([JEP 395](https://openjdk.org/jeps/395)). Ví dụ của bài chạy **Java 17+** theo cú pháp record chuẩn, không dùng `--enable-preview` hay cơ chế reflection tự chế đã lỗi thời. Các phiên bản thư viện cụ thể được nêu là phiên bản có bằng chứng hỗ trợ; khi áp dụng ở dự án thực, vẫn cần kiểm tra tài liệu của chính phiên bản đã cài.

## 1. Vì sao nhận diện `record` chưa đủ để ánh xạ dữ liệu?

Một record được khai báo như sau:

~~~java
public record OrderDto(String orderId, int units) {
    public OrderDto {
        if (orderId == null || orderId.isBlank() || units <= 0) {
            throw new IllegalArgumentException("Invalid order data");
        }
    }
}
~~~

Đoạn này là **định nghĩa kiểu minh họa**, đặt trong tệp `OrderDto.java` nếu dùng `public record` ở cấp cao nhất. Nó có hai component: `orderId` và `units`; canonical constructor nhận (`String`, `int`) đúng thứ tự đó.

Java tạo các accessor `orderId()` và `units()`, **không bắt buộc phải có** `getOrderId()`, `getUnits()` hoặc các setter như một JavaBean thông thường. Component fields là `private final`; record **không có một no-argument constructor ngầm định** chỉ vì nó là kiểu dữ liệu.

Do đó:

- Thư viện chỉ biết tạo object bằng **`new T()` + `setX(...)`** có thể thất bại khi target là record.
- Thư viện hỗ trợ record có thể **đọc component metadata**, chọn constructor phù hợp và truyền các giá trị đã convert theo đúng thứ tự/tên.
- Thư viện tạo được instance nhưng **làm mất/null hóa một trường**, không xử lý danh sách generic, hoặc bỏ qua constructor validation vẫn **chưa đạt yêu cầu mapping của ứng dụng**.
- Thư viện hỗ trợ record trong **đầu vào JSON** chưa chắc hỗ trợ dùng record như **entity có identity và lifecycle trong ORM**.

Cần phân biệt ba lớp năng lực:

| Lớp kiểm tra | Câu hỏi | Có đủ để kết luận thư viện hỗ trợ record không? |
|---|---|---|
| JDK reflection | `Class.isRecord()`, `getRecordComponents()`, canonical constructor có hoạt động? | **Không.** Chỉ chứng minh JVM/JDK thấy metadata record. |
| Cam kết từ thư viện | Tài liệu chính thức có ghi serialize/deserialize/map **Java records** không? Từ phiên bản nào, chiều nào? | **Chưa đủ một mình.** Cần kiểm tra đúng artifact/configuration và use case. |
| Kiểm thử thực tế | Dùng dependency đã giải quyết trong build, round-trip và negative cases có đúng không? | **Có sức thuyết phục nhất** cho phạm vi được kiểm thử; không khẳng định các trường hợp chưa thử. |

**Ý nghĩa “hỗ trợ chính thức”:** Tính năng phải được người duy trì thư viện **ghi nhận trong tài liệu, release notes hoặc hướng dẫn API**, thay vì chỉ có một ví dụ cộng đồng chạy được bằng cách mở private fields/`Unsafe`. Việc thử nghiệm thành công là bằng chứng bổ sung, **không thay thế** cam kết hỗ trợ/phiên bản từ nhà cung cấp.

## 2. JDK reflection tiêu chuẩn dành cho record

Java hiện đại có API chính thức:

~~~java
// Đoạn trích minh họa; giả sử OrderDto đã được khai báo.
Class<?> type = OrderDto.class;
boolean record = type.isRecord();

java.lang.reflect.RecordComponent[] components =
        type.getRecordComponents();

for (java.lang.reflect.RecordComponent component : components) {
    System.out.println(component.getName()
            + " : " + component.getType().getTypeName());
}
~~~

Các điểm cần nhớ:

- `Class.isRecord()` cho biết lớp có phải `record` theo JVM hay không.
- `Class.getRecordComponents()` trả các component theo thứ tự khai báo khi lớp là record; với kiểu không phải record, phương thức trả `null`.
- Mỗi `RecordComponent` có `getName()`, `getType()`, `getGenericType()`, `getAccessor()` và API đọc annotations.
- `Class.getDeclaredConstructor(...)` cho phép tìm constructor có các kiểu tham số tương ứng với components (bao gồm canonical constructor).
- `getDeclaredConstructor(...)` **chỉ chứng minh constructor tồn tại**, không chứng minh mapping framework dùng đúng constructor hoặc được phép gọi nó trong mọi bối cảnh access/JPMS.

Ví dụ nhận diện constructor:

~~~java
// Đoạn trích minh họa; cần import java.lang.reflect.RecordComponent.
RecordComponent[] parts = OrderDto.class.getRecordComponents();
Class<?>[] types = java.util.Arrays.stream(parts)
        .map(RecordComponent::getType)
        .toArray(Class<?>[]::new);

var canonical = OrderDto.class.getDeclaredConstructor(types);
~~~

Phần code trên **không yêu cầu gọi `setAccessible(true)`**; nó chỉ lấy metadata. Thử ép truy cập private constructor/fields và sửa trạng thái `final` bằng reflection không phải chiến lược tương thích record bền vững.

**Kiểm tra annotations đúng nơi:** Một số annotation trên component có thể xuất hiện trên field, accessor, constructor parameter và/hoặc record component tùy `@Target` và quy tắc lan truyền. Mỗi thư viện có chiến lược đọc metadata riêng. Nếu mapping phụ thuộc `@JsonProperty`, `@SerializedName` hoặc một annotation của ORM, phải kiểm thử hành vi **thực tế**, không chỉ thấy một annotation tồn tại ở nơi khác qua reflection.

## 3. Xác nhận phạm vi hỗ trợ theo loại thư viện

Không nên đưa ra kết luận chung “thư viện X hỗ trợ record” mà bỏ qua **dạng ánh xạ**, **phiên bản** và **vai trò của record**.

| Thư viện/hướng dùng | Bằng chứng hỗ trợ chính thức | Phạm vi cần xác minh trong dự án |
|---|---|---|
| **Gson** (JSON ↔ record) | [Gson 2.10 changelog](https://github.com/google/gson/blob/main/CHANGELOG.md) ghi hỗ trợ **serialize và deserialize Java records trên Java 16+**. | Đúng artifact `com.google.code.gson:gson`, phiên bản đã resolved, generic lists, naming policy, null, TypeAdapter tùy biến. |
| **Jackson** (JSON ↔ record) | [Jackson 2.12 release notes](https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.12) ghi hỗ trợ `java.lang.Record`; Jackson **2.x còn được duy trì**, **3.x là dòng mới**. | Xác minh **đúng major**: Jackson 2.x dùng nhóm/package `com.fasterxml.jackson`; Jackson 3.x dùng `tools.jackson` ở nhiều module/API, không nâng cấp bằng cách chỉ đổi version. Kiểm tra annotations/modules và round-trip. |
| **MapStruct** (object ↔ DTO/record) | [MapStruct reference](https://mapstruct.org/documentation/reference-guide/) và [release notes 1.6.3](https://mapstruct.org/news/2024-11-09-mapstruct-1_6_3_bug-fix-released/) có hỗ trợ mapping Java records. | Đây là **mapper sinh mã lúc biên dịch**. Test annotation processor, tạo target qua constructor, source/target names, chính sách null. Không suy ra nó tự xử lý JSON/SQL. |
| **Spring JDBC `DataClassRowMapper`** (SQL row → record) | [Javadoc `DataClassRowMapper`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html) ghi rõ Java records là “data class” được map qua constructor có tên tham số. | Kiểm tra target là top-level hoặc static nested class; tên cột/alias, kiểu JDBC, null cho primitive, constructor mapping, hiệu năng. |
| **Hibernate ORM** (database mapping) | [Hibernate ORM guide — Embeddable objects](https://docs.hibernate.org/stable/orm/introduction/html_single/#entities-embeddable-objects) mô tả `@Embeddable record` như một **value component**. | **Không suy ra `record @Entity` tự nhiên được hỗ trợ.** Phân biệt embeddable, DTO projection, mapped entity, lazy-loading/identifier; xem tài liệu đúng version Hibernate/Jakarta Persistence. |

**Đọc bảng đúng cách:**

1. Tên thư viện không phải chứng cứ; **đúng module + version + mục tiêu dùng** mới quan trọng.
2. Bằng chứng “hỗ trợ đọc/ghi JSON” không tương đương “có thể làm JPA entity”.
3. Bằng chứng “có thể map một record đơn giản” chưa chứng minh mọi annotation, nested record, generic collection hoặc custom converter đều đúng.
4. Khi dự án dùng framework quản lý dependencies (ví dụ Spring Boot BOM), version có hiệu lực thường do BOM/dependency management quyết định, không nhất thiết là phiên bản bạn nhìn thấy trong một tài liệu độc lập.

**Cập nhật phù hợp hệ sinh thái hiện đại:** Tại thời điểm soạn bài (2026), Gson 2.15.0 là một bản phát hành công khai trên Maven Central; Jackson 3.x được dự án Jackson giới thiệu là dòng thích hợp cho dự án mới, trong khi 2.x vẫn được duy trì. Đừng chọn thư viện “càng cũ càng dễ chạy”; dùng nhánh được bảo trì và tương thích với stack đang vận hành.

## 4. Quy trình kiểm tra một thư viện trước khi dùng

### Bước 1 — Xác định chính xác bài toán ánh xạ

Ghi rõ:

- **Nguồn:** JSON object, JSON array, một hàng JDBC, một entity, file CSV hay một object có sẵn?
- **Đích:** record làm **DTO** trả từ API, record làm **request body**, record làm key hoặc record làm **embeddable**?
- **Chiều:** chỉ serialize, chỉ deserialize, hay **hai chiều**?
- **Dữ liệu:** primitive, `String`, `BigDecimal`, `LocalDate`, `enum`, danh sách generic, nested record, record có validation?
- **Yêu cầu:** dữ liệu thiếu/null phải bị từ chối, cho phép trường chưa biết, tên cột camelCase/snake_case, module boundary, native-image?

Ví dụ câu hỏi tốt:

> “Gson 2.15.0 trên JDK 17 có deserialize JSON object thành `OrderDto(String orderId, int units)` bằng canonical constructor, rồi serialize ngược và từ chối số lượng không hợp lệ không?”

Câu hỏi này kiểm thử được. Câu “Gson có hỗ trợ Java 14 không?” vừa rộng vừa lẫn giữa **JDK**, **record preview** và **bản Gson**.

### Bước 2 — Kiểm tra Java target và build dependency thực tế

- `java -version`: JDK chạy.
- `javac --version`: compiler đang dùng.
- `mvn dependency:tree`, hoặc `./gradlew dependencies --configuration runtimeClasspath`: thư viện được resolved, bao gồm transitives.
- `mvn help:effective-pom` hoặc báo cáo dependency-management của framework: xem version do parent/BOM điều khiển.
- Module JSON hoặc annotation processor phù hợp phải nằm ở classpath/processor path khi biên dịch và chạy.

Ví dụ Maven:

~~~bash
java -version
mvn dependency:tree -Dincludes=com.google.code.gson:gson
~~~

Với một project dùng Jackson, tra đầy đủ nhóm modules đi kèm. **Không giả định** có Jackson 3 chỉ vì thấy `jackson-core` có phiên bản 3.x trong một dependency, hoặc Jackson 2 tự động hoạt động cùng mọi dependency dùng package của Jackson 3.

### Bước 3 — Tìm nguồn chính thức

Thứ tự nên ưu tiên:

1. Documentation/release notes/changelog **từ tác giả hoặc nhà duy trì** của thư viện.
2. Javadoc/reference guide và ví dụ do dự án bảo trì.
3. Mã kiểm thử trong repository chính thức, đặc biệt với case mapping record.
4. Issue tracker về giới hạn, regression và xử lý nâng cấp.
5. Bài blog/Q&A cộng đồng chỉ là tham khảo thêm, **không thay thế** nguồn chính thức.

Cần trích ra một kết luận cụ thể: **từ phiên bản nào**, **hỗ trợ chiều mapping nào**, **cần module/plugin nào**, **hạn chế nào**. Nếu tài liệu chỉ nói “POJO mapping” mà không đề cập record, **chưa được phép kết luận** record sẽ hoạt động chỉ vì record có accessor.

### Bước 4 — Kiểm tra JDK reflection nhận diện record

Trước khi đổ lỗi cho library, xác minh:

~~~java
System.out.println(OrderDto.class.isRecord());
System.out.println(
        java.util.Arrays.toString(OrderDto.class.getRecordComponents()));
~~~

Đây chỉ là **sanity check metadata**, không phải chứng minh framework mapping thành công. Dùng `getRecordComponents()` và `getDeclaredConstructor(...)` nếu cần giải thích vì sao một thư viện có thể tạo record mà không có setter.

### Bước 5 — Viết smoke test hai chiều và negative test

Chọn một record nhỏ có constructor validation, một giá trị hợp lệ, một giá trị sai và một list generic; chạy bằng **dependency thực tế**.

Kiểm tra tối thiểu:

- **Đọc:** JSON/dòng dữ liệu → record, đúng giá trị từng component.
- **Ghi:** record → JSON/DTO, nội dung mong đợi (không nhất thiết dựa thứ tự thuộc tính JSON).
- **Round-trip:** record → dữ liệu → record bằng `equals` khi định dạng được thiết kế bảo toàn thông tin.
- **Sai dữ liệu:** validation trong canonical constructor có thực thi không?
- **Generic:** `List<RecordType>` hoặc kiểu chứa record có được map đúng phần tử không?
- **Hạn chế:** thiếu trường, null, sai kiểu, trường thừa, trường đổi tên, nested record, ngày/giờ.

### Bước 6 — Phân loại kết quả và ghi quyết định

| Kết quả | Cách xử lý |
|---|---|
| Docs chính thức có hỗ trợ; smoke test và negative cases đều pass | Chấp nhận trong **phạm vi đã kiểm thử**, lưu version và test trong CI. |
| Có hỗ trợ nhưng sai null/naming/format ngày | Cấu hình đúng module/naming strategy, converter hoặc type adapter; kiểm thử lại. |
| Thư viện chỉ hỗ trợ một chiều | Dùng cho đúng chiều; chuyển đổi chiều còn lại bằng mapper khác hoặc adapter riêng. |
| Thư viện không hỗ trợ record target mà chỉ setter-based JavaBean | Không cố sửa final fields bằng reflection/`Unsafe`; thay thư viện, nâng cấp hoặc chuyển sang DTO class phù hợp. |
| Docs không nói rõ, thử nghiệm pass nhưng không có cam kết | Ghi rõ **chưa xác nhận chính thức**; đánh giá rủi ro nâng cấp và cân nhắc adapter có test. |
| Muốn dùng record làm entity JPA trong khi tài liệu chỉ nói embeddable/DTO | Tách entity và immutable DTO/value record; không giả định các hạn chế JPA đã biến mất. |

## 5. Ví dụ kiểm chứng thật: Gson và Java 17

Mục tiêu là chứng minh **cả metadata reflection và thực tế JSON mapping**. Ví dụ sử dụng:

- **Java 17**: record chuẩn.
- **Gson 2.15.0**: phiên bản công khai hiện hành khi soạn ví dụ, có dòng hỗ trợ record đã được tài liệu Gson xác nhận từ 2.10.
- **Maven** để resolve dependency và chạy; không cần thư viện kiểm thử riêng.

### 5.1. Cấu trúc dự án

~~~text
record-mapping-check/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── RecordMappingSupportCheck.java
~~~

### 5.2. Tệp `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>record-mapping-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.google.code.gson</groupId>
            <artifactId>gson</artifactId>
            <version>2.15.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>RecordMappingSupportCheck</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao chỉ có một dependency?** `Gson` là thư viện JSON cần kiểm thử. Maven xử lý các dependency phụ và plugin tự động; không tự cấu hình `Unsafe` hoặc reflection hack để ép record hoạt động.

**Trong dự án thật:** nếu framework cung cấp BOM/dependency management, hãy đồng bộ phiên bản với cấu hình được hỗ trợ thay vì gắn cứng dependency mới vào một tổ hợp chưa được kiểm thử. POM trên là một **project kiểm chứng độc lập**, không phải chỉ dẫn tự động nâng toàn bộ ứng dụng lên Gson 2.15.0.

### 5.3. Tệp `src/main/java/RecordMappingSupportCheck.java`

~~~java
import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class RecordMappingSupportCheck {

    public record OrderDto(String orderId, int units) {
        public OrderDto {
            Objects.requireNonNull(orderId, "orderId");
            if (orderId.isBlank() || units <= 0) {
                throw new IllegalArgumentException("Invalid order data");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Class<OrderDto> type = OrderDto.class;

        // (1) JDK reflection: record shape và canonical constructor.
        System.out.println("isRecord=" + type.isRecord());
        RecordComponent[] parts = type.getRecordComponents();

        String componentNames = Arrays.stream(parts)
                .map(c -> c.getName() + ":"
                        + c.getType().getSimpleName())
                .collect(Collectors.joining(","));
        System.out.println("components=" + componentNames);

        Class<?>[] types = Arrays.stream(parts)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);
        System.out.println("canonical="
                + (type.getDeclaredConstructor(types) != null));

        Gson gson = new Gson();

        // (2) JSON -> record: kiểm tra dữ liệu đến đúng components.
        OrderDto order = gson.fromJson(
                "{\"orderId\":\"A-7\",\"units\":2}", OrderDto.class);
        System.out.println("read=" + order);

        // (3) record -> JSON -> record: so sánh bằng equals của record.
        String json = gson.toJson(order);
        System.out.println("roundTrip=" +
                order.equals(gson.fromJson(json, OrderDto.class)));

        // (4) Generic list: giữ kiểu OrderDto, không chỉ List raw.
        Type listType = new TypeToken<List<OrderDto>>() {}.getType();
        List<OrderDto> rows = gson.fromJson(
                "[{\"orderId\":\"A-7\",\"units\":2}]", listType);
        System.out.println("listSize=" + rows.size());

        // (5) Negative test: canonical constructor phải từ chối units=0.
        boolean invalidRejected;
        try {
            gson.fromJson(
                    "{\"orderId\":\"A-7\",\"units\":0}", OrderDto.class);
            invalidRejected = false;
        } catch (RuntimeException ex) {
            // Không phụ thuộc lớp exception wrapper của phiên bản thư viện.
            invalidRejected = true;
        }
        System.out.println("invalidRejected=" + invalidRejected);
    }
}
~~~

**Điểm QA quan trọng:** `invalidRejected=true` chỉ chứng minh lời gọi đã ném một `RuntimeException` ở trường hợp dữ liệu sai. Khi làm kiểm thử sản phẩm, nên kiểm tra sâu **nguyên nhân** và kiểu ngoại lệ cụ thể để phân biệt lỗi validation đúng chủ đích với lỗi mapping/visibility không mong muốn. Trong ví dụ ngắn này, các đường thành công và reflection đều chạy trước negative test, làm kết luận đáng tin cậy hơn.

### 5.4. Chạy và đầu ra

Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

**Đầu ra thực tế đã kiểm chứng bằng Maven và Java compiler sử dụng `release 17`:**

~~~text
isRecord=true
components=orderId:String,units:int
canonical=true
read=OrderDto[orderId=A-7, units=2]
roundTrip=true
listSize=1
invalidRejected=true
~~~

**Diễn giải chính xác:**

1. `isRecord=true` cho biết đây là record theo JDK.
2. `components=orderId:String,units:int` chứng minh tên, kiểu và thứ tự các components.
3. `canonical=true` cho biết constructor mang đúng kiểu tham số của các components tồn tại.
4. `read=OrderDto[...]` chứng minh JSON đầu vào tạo đối tượng với hai giá trị mong đợi.
5. `roundTrip=true` dùng `equals` của record, không phụ thuộc thứ tự hai thuộc tính trong văn bản JSON.
6. `listSize=1` cho thấy `TypeToken<List<OrderDto>>` cho phép biểu diễn kiểu phần tử generic khi deserialize.
7. `invalidRejected=true` là kết quả khi JSON cung cấp `units=0`, trái invariant `units > 0` trong canonical constructor.

**Phạm vi kết luận hợp lệ:** Test này xác nhận Gson 2.15.0 với record ví dụ trên chạy theo các đường đã kiểm thử. Nó **không** có nghĩa mọi record generic phức tạp, mọi annotation, mọi giá trị `null`, mọi cấu hình runtime hoặc mọi thư viện khác đều được hỗ trợ như nhau.

## 6. Mở rộng checklist test để kiểm tra “hỗ trợ chính thức” trong hệ thống

Bài test trên là điểm khởi đầu. Khi đưa record vào API thực, tạo các test nhỏ có tên và kỳ vọng riêng.

| Test | Đầu vào hoặc thao tác | Điều cần khẳng định |
|---|---|---|
| Record nguyên thủy | `record Pair(String key, int value)` | Tạo đúng canonical constructor, không cần setter. |
| Record một component | `record Code(String value)` từ `{"value":"A"}` | JSON object hay scalar được xử lý đúng **theo hợp đồng phiên bản và cấu hình**. |
| Đổi tên thuộc tính | JSON `"order_id"`, component `orderId` | Naming strategy/annotation thật sự áp dụng với record. |
| Record lồng record | `record Outer(Inner inner)` | Mapped đúng inner, không thay bằng `Map` không định kiểu. |
| Generic collection | `List<OrderDto>` | Phần tử là `OrderDto`, không chỉ `LinkedTreeMap` hay `Map`. |
| Dữ liệu thiếu | Thiếu `units` hoặc `orderId` | Giá trị mặc định/null hoặc báo lỗi **đúng chính sách**; không âm thầm coi “missing” là hợp lệ. |
| Explicit `null` | `{"orderId":null,"units":2}` | Bị từ chối/được xử lý đúng theo validation và cách framework bọc lỗi. |
| Sai kiểu | `{"units":"not-number"}` | Chuyển đổi số lỗi rõ ràng; không trả giá trị sai âm thầm. |
| Trường thừa | JSON có `"extra":...` | Theo cấu hình, bỏ qua hoặc báo lỗi; không mặc định tất cả library giống nhau. |
| Kiểu ngày giờ | `LocalDate`, `Instant` | Đúng module/adapter và chuẩn hóa timezone theo thiết kế. |
| Invariant giữa fields | `start < end` trong compact constructor | Mapping không bỏ qua constructor validation. |
| Access/nested type | Top-level, `public static` nested record | Mapping được trong môi trường thực; phân biệt với local record/record private. |
| Module/native image | Ứng dụng có `module-info.java` hoặc native build | Cấu hình `opens`/reflection/metadata phù hợp với library, không lỗi lúc deploy. |
| Tính ổn định khi nâng cấp | Chạy cùng test trên release hiện hành + dependency tree | Bắt regression về naming, constructor, coercion, annotation handling. |

**Không nên dùng duy nhất `assertNotNull(result)`:** một đối tượng record không null vẫn có thể sai `units` hoặc `orderId`, nhất là khi dữ liệu đến từ schema thay đổi. So sánh **từng component** và thực hiện kiểm thử lỗi có chủ đích.

### Một cách viết test phản chứng tốt

Với mã Gson ở phần 5, thay riêng JSON:

~~~json
{"orderId":"A-7","units":0}
~~~

Nếu `units > 0` là bất biến, mapping phải **không tạo ra một `OrderDto` hợp lệ giả**. Khi framework bọc ngoại lệ từ constructor, test nên xác minh nguyên nhân nội bộ (nếu API cho phép) và tránh kết luận “hỗ trợ” chỉ từ việc nó ném bất kỳ exception nào.

Nếu thiếu `units`, **không tự giả định** thư viện sẽ ném lỗi. Với một primitive `int`, các thư viện/configuration khác nhau có thể dùng giá trị mặc định hoặc có chính sách thiếu thuộc tính riêng. Đây là lý do bắt buộc kiểm thử “missing” tách biệt với “explicit null”.

## 7. Đi sâu theo từng nhóm mapper

### 7.1. Gson và Jackson — JSON mapping

Cả Gson và Jackson đều là thư viện JSON, nhưng **API và chính sách mặc định không giống nhau**.

- **Gson:** tài liệu changelog chính thức nêu hỗ trợ record từ 2.10 khi JVM là Java 16 trở lên; dùng `Gson.toJson` và `Gson.fromJson`. Với generic, truyền `TypeToken` hoặc `Type` đủ thông tin.
- **Jackson:** record support được thêm ở Jackson 2.12, với khả năng đọc/ghi bằng record accessors/constructor. Với một record chỉ có **một component**, Jackson 2.12 thay đổi mặc định để dùng **property-based binding**; đừng dựa vào hành vi kiểu “scalar” của một bản rất cũ.
- **Jackson major 3:** dự án Jackson đã đổi namespace của nhiều module/API sang `tools.jackson` và yêu cầu Java 17+. Nếu đang duy trì Spring hoặc hệ thống dùng Jackson 2.x, nâng version phải dựa trên **compatibility guide**, không chỉ thay một chữ số ở POM. Chọn nhánh bảo trì phù hợp hệ sinh thái, không trộn Java packages và annotation modules tùy ý.

Ví dụ khai báo kiểu cho JSON:

~~~java
record CustomerResponse(String customerId, int points) {}
~~~

Đoạn trên **chỉ minh họa kiểu**, không phải chương trình đầy đủ. Thư viện JSON cần map tên thuộc tính JSON vào `customerId`, `points` và truyền đúng giá trị cho constructor; không thể giả định sẽ gọi setter `setCustomerId` vì record không có setter.

Các tiêu chí riêng cho JSON còn gồm: chính sách null, bỏ qua/không bỏ qua trường lạ, hỗ trợ `enum`, kiểu thời gian, serialization format và cấu hình naming strategy.

### 7.2. MapStruct — object-to-object mapping lúc biên dịch

MapStruct sinh mã ánh xạ tại **compile time**. Với target record, generated mapper thường phải đi theo kiểu **constructor-based mapping** thay vì setter-based mapping.

Điều cần kiểm tra:

1. Version `mapstruct` **và** `mapstruct-processor`.
2. Annotation processing đã bật và class generated thực sự xuất hiện.
3. Source property được tìm đúng tên; target component được truyền đúng vào constructor.
4. Chuyển đổi `null`, kiểu số, collection, nested DTO và mapping custom theo chính sách.
5. Code generated compile và unit tests pass trên đúng JDK project dùng.

**Không suy ra** “MapStruct hỗ trợ Java records” tức là nó xử lý luôn JSON hoặc nắm mọi chính sách ORM. Nó ánh xạ giữa object được định nghĩa trong Java; JSON parsing và persistence là trách nhiệm của tầng khác.

### 7.3. Spring JDBC — ánh xạ hàng SQL

Spring cung cấp `DataClassRowMapper` với tài liệu chính thức ghi hỗ trợ Java records (cùng với Kotlin data classes và lớp có constructor theo tên tham số). Ví dụ minh họa API:

~~~java
// Đoạn trích, không độc lập; cần Spring JDBC trên classpath.
record UserRow(long id, String displayName) {}

var rowMapper =
        new org.springframework.jdbc.core.DataClassRowMapper<>(UserRow.class);
~~~

Lưu ý **quan trọng về phạm vi kiểu**: Javadoc yêu cầu class target là **top-level hoặc static nested**. `UserRow` bên trên là record cấp tệp nếu khai báo ngoài một phương thức; không dùng **local record bên trong method** làm target mặc định rồi suy ra sẽ hoạt động. Khi dùng SQL:

- `SELECT user_id AS id, display_name AS display_name` phải có quy tắc nối tên tương thích với `id` và `displayName` (kiểm tra behavior thực tế theo library).
- Null từ database vào component primitive cần chính sách rõ ràng.
- Kiểu JDBC và kiểu Java phải chuyển đổi được, nhất là ngày/giờ, `BigDecimal`, UUID.
- `DataClassRowMapper` ưu tiên tính tiện dụng hơn hiệu năng tối đa; với hot path quan trọng, custom `RowMapper` có thể thích hợp.

Đây là **mapping từ SQL row sang object**, không tự biến record thành một JPA entity.

### 7.4. Hibernate ORM — phân biệt record value và entity

JPA/Hibernate quản lý **entity identity, lifecycle, dirty checking và quan hệ persistence**. Một record có các component fields final và không có no-arg constructor tự sinh; nó phù hợp với **value object/DTO** hơn là một mutable entity truyền thống.

Tài liệu Hibernate hiện đại cho phép dùng record làm **`@Embeddable`** trong ngữ cảnh được hỗ trợ:

~~~java
// Đoạn minh họa, chỉ dùng trong project đã cấu hình Jakarta Persistence/Hibernate.
@jakarta.persistence.Embeddable
public record Name(String firstName, String lastName) {}
~~~

Với record embeddable, yêu cầu no-args constructor được xử lý theo khả năng của Hibernate phiên bản phù hợp. **Không tự suy ra** từ ví dụ này rằng `@Entity public record User(...)` là mapping entity đầy đủ hoặc portable theo mọi chuẩn Jakarta Persistence.

Nếu cần trả record từ truy vấn, cân nhắc **DTO projection** bằng constructor/projection API được ORM hỗ trợ; đó là một bài toán khác với persist record như entity.

**Quy tắc thực dụng:** Trước khi đổi entity class sang record, kiểm tra chính xác: có cần identity/proxy/no-arg constructor không, lazy loading thế nào, phiên bản Hibernate và Jakarta Persistence là gì, kiểu dữ liệu đó là entity hay immutable value/DTO? Đừng trộn vai trò.

## 8. Những lỗi thường gặp khi đánh giá record compatibility

| Sai lầm | Hậu quả | Cách kiểm tra/sửa |
|---|---|---|
| Thấy `clazz.isRecord() == true` rồi kết luận framework map được | Reflection JDK hoạt động nhưng mapper có thể vẫn đòi setter/no-arg constructor | Chạy deserialize/map thực tế với dependency hiện dùng. |
| Chỉ thử serialize mà không thử deserialize | Thư viện có thể ghi JSON từ accessor nhưng không khởi tạo record | Test hai chiều, nhất là canonical constructor và dữ liệu thiếu. |
| Dựa vào câu trả lời cộng đồng mà bỏ qua phiên bản | Kết quả đúng với một release nhưng sai trên release project dùng | Chỉ dùng official docs/release notes đúng version và test. |
| Dùng dependency do BOM kéo về mà không biết | Code theo tài liệu phiên bản khác, hành vi null/naming khác | Đọc dependency tree và effective POM/Gradle graph. |
| Cố gọi setter trên record | Record không có setters theo component | Dùng mapper có constructor-based record support. |
| Giả định `@JsonProperty` hoặc `@Column` luôn được mọi thư viện đọc giống nhau | Tên component bị map nhầm; annotations ở nhiều target khác nhau | Kiểm tra tài liệu annotation, đặt test đổi tên và chạy đúng provider. |
| Mapping thành công nhưng bỏ qua invariant | Record chứa giá trị sai, dữ liệu âm hoặc null | Thêm compact constructor validation, test negative cases. |
| Dùng `List.class` thay vì generic token | Mất kiểu phần tử, phần tử thành `Map` hoặc kiểu trung gian | Dùng `TypeToken<List<T>>` (Gson) hay generic type API tương đương. |
| Giả định JSON object một trường tương đương JSON scalar | Khác contract và có thể đổi giữa versions | Kiểm thử đúng JSON shape, cấu hình creator khi thư viện hỗ trợ. |
| Giả định SQL mapper và JSON mapper có cùng naming convention | Sai `snake_case` ↔ `camelCase`, null hoặc kiểu ngày | Test từng tầng và aliases/converters cụ thể. |
| Cho rằng `@Embeddable record` đồng nghĩa `@Entity record` | Lỗi mô hình ORM, proxy/lifecycle/identity | Tách DTO/value record khỏi entity, đối chiếu guide đúng version. |
| Dựa vào reflection mở field final/`Unsafe` | Mất invariant, vi phạm module encapsulation, dễ vỡ ở JDK mới | Ưu tiên canonical constructor và adapter chính thức. |
| Không kiểm tra JPMS/native-image | Chạy local JVM được nhưng lỗi khi deploy | Kiểm thử môi trường build/runtime thực, cấu hình metadata và quyền truy cập cần thiết. |
| Kết luận “hỗ trợ mọi record” sau một smoke test | Bỏ sót generic, nested, recursive, null và custom adapter | Có ma trận compatibility theo các cấu trúc thực dùng. |

## 9. Checklist dùng để quyết định trong code review

Khi một pull request muốn thay JavaBean DTO bằng record, có thể ghi bảng sau trong phần mô tả:

| Hạng mục | Bằng chứng cần có |
|---|---|
| **JDK** | Java target/runtime từ 16+; dự án biên dịch/có thể chạy record chuẩn, ví dụ `--release 17`. |
| **Vai trò dữ liệu** | JSON request/response, mapper DTO, SQL row mapper hay ORM embeddable? Không nhập nhằng với entity. |
| **Thư viện & module** | Tên artifact, resolved version, processor/add-on modules đã xác nhận. |
| **Chứng cứ chính thức** | URL release note/Javadoc có nêu rõ record support và phạm vi. |
| **Mapping hợp lệ** | Đọc/ghi đúng components, không mất dữ liệu và không phụ thuộc thứ tự JSON object. |
| **Canonical constructor** | Có được gọi và kiểm tra bất biến? Dữ liệu sai bị từ chối đúng cách? |
| **Biên dữ liệu** | Missing/null, tên thuộc tính, kiểu số, ngày giờ, generic, nested, unknown property được thử. |
| **Môi trường chạy** | Unit + integration test trên JVM/module/native target thực tế. |
| **Nâng cấp** | CI giữ regression tests; có kế hoạch xử lý khác biệt major version. |

**Quy tắc kết luận:** Viết “*Gson 2.15.0 hỗ trợ JSON ↔ `OrderDto` của dự án, đã thử read/write/list/validation trên JDK 17*” thì có thể kiểm chứng. Không nên viết “*bất kỳ thư viện mapping nào cũng hỗ trợ record vì Java 14 có record*”.

## 10. Bài luyện tập

**Câu 1 — Reflection hay mapping?** `OrderDto.class.isRecord()` trả `true`, nhưng mapper báo không tìm thấy setter `setUnits`. Có thể kết luận gì?

**Đáp án:** JDK nhận diện record chính xác, nhưng mapper hiện tại chưa chứng minh có record constructor mapping. Xem official docs của đúng phiên bản, kiểm tra configuration; có thể cần nâng cấp hoặc thay mapper. Không thêm setter để sửa record.

**Câu 2 — Thư viện khác nhiệm vụ.** Dự án dùng MapStruct 1.6.3 để đổi entity sang DTO record, nhưng deserialize JSON thành DTO lỗi. MapStruct đã “không hỗ trợ record” chưa?

**Đáp án:** Chưa. MapStruct xử lý object-to-object mapping ở compile time; JSON deserialize do thư viện HTTP/JSON như Gson hoặc Jackson. Phải xác định tầng lỗi và kiểm tra đúng thư viện.

**Câu 3 — Dùng record với Hibernate.** Một nhóm thấy tài liệu Hibernate cho phép `@Embeddable record Name(...)` và muốn chuyển mọi `@Entity` thành record. Đây có phải kết luận hợp lệ không?

**Đáp án:** Không. `@Embeddable` là value component; entity có yêu cầu identity và lifecycle riêng. Đối chiếu tài liệu đúng phiên bản và cân nhắc record cho DTO/value object/projection trước.

**Câu 4 — Record một component.** Một endpoint cũ nhận JSON scalar `"A-7"`, một endpoint mới dùng `record Code(String value)` và JSON object `{"value":"A-7"}`. Vì sao cần test trước khi nâng Jackson?

**Đáp án:** Jackson đã có thay đổi hành vi mặc định với **single-component records** từ 2.12 (properties-based binding). JSON scalar và JSON object là hai contract khác nhau; cần xác nhận version, config và compatibility với client.

**Câu 5 — Test âm tính.** Chỉ kiểm tra `gson.fromJson(validJson, OrderDto.class) != null` đã đủ chưa?

**Đáp án:** Chưa. Kiểm tra giá trị từng component, round-trip, null/missing fields, generic list và việc constructor validation từ chối dữ liệu sai. Một object không null có thể chứa dữ liệu không hợp lệ.

**Câu 6 — Version conflict.** Dependency trực tiếp là Gson 2.15.0 nhưng runtime chọn một Gson khác theo dependency management. Nên báo “đã test Gson 2.15.0 trên production” chưa?

**Đáp án:** Không. Phải xem **resolved runtime dependency**, sửa xung đột hoặc test đúng dependency mà runtime thật nạp. Tên version trong một file build chưa đủ chứng minh.

## Tài liệu chính thức

- [OpenJDK — JEP 395: Records](https://openjdk.org/jeps/395): records được chuẩn hóa tại Java 16.
- [Oracle Java 17 API — `Class.isRecord()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isRecord()): API nhận diện record.
- [Oracle Java 17 API — `Class.getRecordComponents()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getRecordComponents()): API đọc components.
- [Oracle Java 17 API — `RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html): tên, kiểu, generic type, accessor và annotations.
- [Gson changelog](https://github.com/google/gson/blob/main/CHANGELOG.md): hỗ trợ JSON serialize/deserialize Java records từ 2.10 trên Java 16+.
- [Gson releases](https://github.com/google/gson/releases): thông tin phát hành, gồm các bản 2.15.x hiện đại.
- [Gson User Guide](https://github.com/google/gson/blob/main/UserGuide.md): cách dùng API, dependency và generic type.
- [Jackson Release 2.12](https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.12): hỗ trợ `java.lang.Record` và trường hợp record một component.
- [Jackson Project Portal](https://github.com/FasterXML/jackson): nhánh 2.x/3.x, tình trạng duy trì và hướng dẫn nâng major version.
- [MapStruct Reference Guide](https://mapstruct.org/documentation/reference-guide/): generator mapper và hỗ trợ các kiểu target/source.
- [MapStruct 1.6.3 release notes](https://mapstruct.org/news/2024-11-09-mapstruct-1_6_3_bug-fix-released/): các sửa lỗi liên quan tới record mapping.
- [Spring JDBC DataClassRowMapper Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html): hỗ trợ Java record qua constructor mapping và giới hạn target type.
- [Hibernate ORM — A Short Guide](https://docs.hibernate.org/stable/orm/introduction/html_single/): mô hình `@Embeddable` với record và khác biệt entity/value component.
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): cách dùng `--release` và kiểm tra mức Java.
- [Maven Exec Plugin](https://www.mojohaus.org/exec-maven-plugin/): chạy chương trình Java trong project Maven.

**Ghi nhớ:** **Java reflection thấy record không có nghĩa data mapper hỗ trợ record chính thức.** Hãy tìm bằng chứng từ nhà cung cấp cho **đúng module/phiên bản/phạm vi**, đối chiếu dependency runtime, rồi chạy smoke test **constructor + đọc/ghi + generic + dữ liệu sai**. Chỉ chấp nhận kết luận tương thích cho những trường hợp đã được kiểm chứng và đưa các kiểm thử đó vào CI.