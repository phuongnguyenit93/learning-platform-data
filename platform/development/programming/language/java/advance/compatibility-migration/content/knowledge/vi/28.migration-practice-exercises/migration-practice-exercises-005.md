# So sánh API trước và sau thay đổi bằng công cụ tự động

Khi nâng cấp Java, framework hoặc một thư viện được nhiều ứng dụng dùng chung, việc nhìn vào hai file source rồi nhận xét “có vẻ không thay đổi nhiều” là không đủ. Một phương thức bị đổi kiểu trả về, một interface được bổ sung abstract method hay một package không còn được export đều có thể khiến ứng dụng bên sử dụng biên dịch lỗi hoặc gặp `NoSuchMethodError` ở runtime. Ngược lại, một thay đổi nhìn có vẻ lớn trong implementation nhưng không làm thay đổi public API có thể hoàn toàn không ảnh hưởng tới phần lớn consumer.

**So sánh API tự động** (*automated API comparison*) giúp xác định những khác biệt có cấu trúc giữa hai phiên bản thư viện. Công cụ phân tích class file, chữ ký, modifiers, quan hệ kế thừa hoặc thông tin API để tạo báo cáo những thành phần được thêm, xóa và thay đổi. Trong một migration đáng tin cậy, báo cáo này được kết hợp với **biên dịch lại mã consumer**, **thử binary đã biên dịch từ trước** và **kiểm thử hành vi**.

Đây là bài thực hành thuộc chương **Bài thực hành** của module **Java Advance Compatibility Migration**. Người học sẽ tạo hai bản JAR nhỏ, chạy công cụ tự động để tìm API break, xác nhận từng loại bằng compiler/runtime, sau đó xây dựng quality gate có thể áp dụng cho một thư viện Java thực tế.

## 1. Mục tiêu của bài thực hành

Sau khi thực hành, bạn có thể:

1. Phân biệt **public API**, **binary interface (ABI)**, **source compatibility** và **behavioral compatibility**.
2. Tạo hai JAR cùng tọa độ thư viện nhưng khác phiên bản, với những thay đổi API có chủ đích.
3. Sử dụng `javap` và công cụ so sánh JAR như **japicmp** để thu thập khác biệt có thể tái lập.
4. Nhận diện method bị xóa, đổi return type, thu hẹp visibility, thêm interface method và overload mới.
5. Giải thích vì sao một báo cáo “binary compatible” không đủ để chứng minh mọi source consumer còn compile.
6. Biên dịch lại consumer với bản cũ/mới để nhận diện source breaks, đặc biệt overload ambiguity.
7. Chạy binary client cũ với thư viện mới để phát hiện linkage errors.
8. Lập báo cáo API differences có bằng chứng, phân loại mức độ ảnh hưởng và đưa vào CI.
9. Nhận biết giới hạn của công cụ khi gặp JPMS, multi-release JAR, reflection, serialization và thay đổi hành vi.
10. Đề xuất cách giữ compatibility hoặc hướng dẫn consumer migration khi breaking change là chủ đích.

## 2. Bối cảnh: vì sao cần so sánh API khi nâng Java?

Giả sử thư viện `billing-api` được dùng bởi ba dịch vụ:

```text
billing-api 1.x
    |
    +----> checkout-service
    +----> invoice-batch
    +----> reporting-service
```

Nhóm sở hữu thư viện chuẩn bị nâng JDK và framework, đồng thời phát hành `billing-api 2.x`. Một số thay đổi chỉ là implementation; một số tác động trực tiếp đến các consumer:

- Đổi kiểu trả về của method.
- Bỏ public constructor.
- Chuyển method `public` thành package-private.
- Đổi tên class hoặc package.
- Thêm overload có thể làm lời gọi cũ mơ hồ.
- Thêm abstract method vào interface mà consumer tự implement.
- Thay `module-info.java`, khiến package không còn visible.
- Đổi generic signature hoặc annotation processing contract.

Nếu chỉ build `billing-api 2.x`, tất cả những thay đổi trên có thể vẫn hợp lệ đối với source của chính thư viện. Phần bị hỏng nằm ở **mã của người sử dụng**, vốn không nhất thiết có trong unit tests của thư viện.

Một pipeline tốt cần trả lời ba câu hỏi khác nhau:

| Câu hỏi | Cách kiểm tra trọng tâm |
| --- | --- |
| API/ABI của v1 và v2 thay đổi chỗ nào? | Công cụ tự động đọc hai JAR, ví dụ japicmp hoặc Revapi. |
| Source consumer cũ còn compile với v2 không? | Recompile **cùng một snapshot source** với v1 và v2. |
| Binary consumer cũ còn link và chạy với v2 không? | Chạy class/JAR đã compile từ v1 với thư viện v2, kết hợp kiểm tra ABI. |

Ngoài ra, khi **behavior thay đổi nhưng chữ ký không đổi**, phải dùng regression/contract tests. Không có công cụ API diff nào có thể tự chứng minh toàn bộ logic nghiệp vụ vẫn đúng.

## 3. Khái niệm cốt lõi trước khi chạy công cụ

### 3.1. Public API

Public API không chỉ là danh sách mọi method có modifier `public`. Hợp đồng thực tế còn có thể bao gồm:

- Public/protected types, constructors, methods và fields được cam kết hỗ trợ.
- Generic bounds, annotations và checked exceptions liên quan đến source consumer.
- Abstract/default methods của interface.
- Type hierarchy và các khả năng subclass/implement.
- Exported packages và module names với JPMS.
- Public configuration keys, service interfaces hoặc wire schemas nếu chúng là hợp đồng của sản phẩm.

Công cụ so sánh JAR thường tập trung vào **Java class-file/API surface**. Các loại hợp đồng nằm ngoài bytecode, như HTTP JSON schema và SQL schema, đòi công cụ hoặc test khác.

### 3.2. ABI và binary compatibility

Ở JVM, lời gọi method tham chiếu tên và descriptor liên quan đến parameter/return types. Ví dụ:

```java
public int total(int base, int tax);
```

Descriptor của method có dạng:

```text
(II)I
```

Nếu đổi return type thành `long`:

```java
public long total(int base, int tax);
```

Descriptor mới là:

```text
(II)J
```

Consumer binary được compile với descriptor cũ có thể gặp `NoSuchMethodError` khi chạy với JAR mới, dù tên method trong source vẫn là `total`.

### 3.3. Source compatibility

Một thay đổi có thể **giữ binary compatibility** mà vẫn làm consumer source cũ khó biên dịch lại. Ví dụ thêm một overload mới có thể khiến lời gọi `format("abc")` trở nên mơ hồ.

Do đó, nếu công cụ báo một thay đổi không phá binary interface, ta vẫn cần kiểm tra source compatibility, đặc biệt đối với:

- Overload resolution.
- Generics và type inference.
- Lambda và method references.
- Interface implementation.
- Checked exceptions.
- Java language level và annotation processors.

### 3.4. Behavioral compatibility

Thay logic tính thuế từ “làm tròn xuống” thành “làm tròn gần nhất” có thể không đổi bất kỳ chữ ký Java nào. API diff báo không có thay đổi, nhưng dữ liệu hóa đơn thay đổi.

Vì vậy, trong report nên tách kết quả thành:

```text
API/ABI changes   -> kiểm tra tự động trên JAR
Source compatibility -> recompile consumer
Binary runtime    -> thử consumer binary cũ
Behavior          -> regression/contract/integration tests
```

## 4. Công cụ dùng trong bài thực hành

| Công cụ | Vai trò | Điều không nên suy ra từ kết quả |
| --- | --- | --- |
| `javap` (JDK) | Hiển thị chữ ký bytecode, modifiers và method descriptors. | Không tự phân loại toàn bộ quy tắc compatibility. |
| `diff` / `git diff` | So sánh hai bản output chữ ký dưới dạng văn bản. | Text diff không hiểu đầy đủ quan hệ Java language/JVM. |
| **japicmp** | So sánh hai JAR, nhận diện API changes và các dạng binary/source incompatibility mà công cụ hỗ trợ. | Không đảm bảo mọi consumer source/behavior đều tương thích. |
| **Revapi** | Phân tích API changes với cơ chế extensions, filters và policy/reporting. | Cần cấu hình đúng extension, artifact và phạm vi API. |
| `javac` / Maven / Gradle | Biên dịch lại source consumer với artifact candidate. | Compile PASS không chứng minh binary cũ hoặc behavior đúng. |
| `java` | Chạy binary client cũ với library mới. | Một vài runtime calls không bao phủ mọi code path. |
| `jdeps` | Khảo sát phụ thuộc tĩnh, đặc biệt API nội bộ JDK hoặc module dependencies. | Không phát hiện đầy đủ reflection và dynamic class loading. |

Trong lab này, **japicmp** là công cụ so sánh API chính; `javap` dùng để giải thích kết quả; Maven giúp tạo hai JAR và compile consumer. Revapi được giới thiệu như lựa chọn thay thế/đi sâu hơn cho CI.

**Lưu ý phiên bản công cụ:** ví dụ Maven bên dưới cố định `maven-compiler-plugin 3.13.0` và Java release 17 để minh họa. Đối với japicmp/Revapi, hãy chọn bản CLI/plugin được tài liệu của chính công cụ xác nhận hỗ trợ JDK/class-file version đang phân tích. Không coi một bản ví dụ trong bài là “latest” hay bảo đảm hoạt động trên mọi JDK tương lai.

## 5. Sơ đồ bài lab

Ta dựng ba project tách biệt:

```text
api-comparison-lab/
├── api-v1/
│   ├── pom.xml
│   └── src/main/java/com/example/api/
│       ├── PriceCalculator.java
│       └── PaymentPlugin.java
├── api-v2/
│   ├── pom.xml
│   └── src/main/java/com/example/api/
│       ├── PriceCalculator.java
│       └── PaymentPlugin.java
├── consumer/
│   ├── pom.xml
│   └── src/main/java/com/example/consumer/
│       ├── CheckoutClient.java
│       └── ExternalPaymentPlugin.java
└── reports/                 # Nơi lưu API diff và compile logs
```

Hai project `api-v1` và `api-v2` cố ý có cùng Maven `groupId` và `artifactId` nhưng version khác nhau:

```text
com.example.lab:sample-api:1.0.0
com.example.lab:sample-api:2.0.0
```

Consumer dùng version được truyền qua property, để so sánh khi **không thay source**.

### 5.1. Yêu cầu môi trường

- JDK 17 hoặc một JDK phù hợp với `--release 17` của lab.
- Maven 3.x tương thích với JDK đã chọn.
- Một trình soạn thảo văn bản để tạo các file.
- japicmp CLI JAR từ bản phát hành chính thức của dự án, có thể chạy bằng JDK đã chọn.
- Một shell phù hợp; các lệnh minh họa dùng Bash. Trên Windows có thể dùng PowerShell với đường dẫn và lệnh tương đương.

Các lệnh kiểm tra môi trường:

```bash
java -version
javac -version
mvn -version
```

Không nhất thiết cần một framework lớn hoặc database. Mục tiêu của lab là cô lập **Java API changes**.

### 5.2. Các thay đổi được cài đặt có chủ đích

| ID | Thay đổi từ v1 sang v2 | Dự đoán ban đầu |
| --- | --- | --- |
| A1 | `total(int,int)` đổi return từ `int` sang `long`. | Source và binary consumer có thể hỏng. |
| A2 | `flush()` từ `public` thành package-private. | Code ngoài package không được phép gọi. |
| A3 | Thêm `normalize(Serializable)` bên cạnh `normalize(CharSequence)`. | Binary cũ có thể vẫn chạy; source `normalize("text")` có thể mơ hồ. |
| A4 | `PaymentPlugin` thêm abstract method `audit()`. | Concrete implementer ở consumer phải cập nhật. |
| A5 | Thay đổi implementation của method nhưng giữ signature. | API diff có thể không báo; cần behavior tests. |

Hãy giữ source consumer của v1 đến cuối phép so sánh; việc sửa trước khi đo sẽ che các source breaks cần phát hiện.

## 6. Tạo project API v1

### 6.1. File `api-v1/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.lab</groupId>
    <artifactId>sample-api</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. File `api-v1/src/main/java/com/example/api/PriceCalculator.java`

```java
package com.example.api;

public class PriceCalculator {
    public int total(int base, int tax) {
        return base + tax;
    }

    public String normalize(CharSequence value) {
        return value.toString().trim();
    }

    public void flush() {
        // V1: public API, chỉ minh họa.
    }
}
```

### 6.3. File `api-v1/src/main/java/com/example/api/PaymentPlugin.java`

```java
package com.example.api;

public interface PaymentPlugin {
    String name();
}
```

Bản v1 có một contract đơn giản: consumer gọi method `total`, `normalize`, `flush` và có thể triển khai interface `PaymentPlugin`.

## 7. Tạo API v2 với những thay đổi cần phát hiện

### 7.1. File `api-v2/pom.xml`

Nội dung giống `api-v1/pom.xml`, chỉ thay:

```xml
<version>2.0.0</version>
```

Giữ nguyên `groupId`, `artifactId`, compiler plugin và Java release để cô lập ảnh hưởng của API.

### 7.2. File `api-v2/src/main/java/com/example/api/PriceCalculator.java`

```java
package com.example.api;

import java.io.Serializable;

public class PriceCalculator {
    // A1: đổi return type; method descriptor thay đổi.
    public long total(int base, int tax) {
        return (long) base + tax;
    }

    // Method cũ còn nguyên chữ ký.
    public String normalize(CharSequence value) {
        return value.toString().trim();
    }

    // A3: thêm overload có thể làm source consumer mơ hồ.
    public String normalize(Serializable value) {
        return value.toString().trim();
    }

    // A2: từ public thành package-private.
    void flush() {
        // Không còn là public API.
    }
}
```

### 7.3. File `api-v2/src/main/java/com/example/api/PaymentPlugin.java`

```java
package com.example.api;

public interface PaymentPlugin {
    String name();

    // A4: concrete implementer cũ cần thêm method này.
    void audit();
}
```

### 7.4. Vì sao v2 tự nó vẫn compile?

Không có lỗi Java source trong việc đổi return type, thu hẹp visibility hoặc thêm abstract method vào interface khi **chỉ biên dịch chính library v2**. Nếu library không chứa các consumer cũ, build v2 có thể thành công.

Đó là bài toán mà API comparison và consumer recompilation giải quyết.

## 8. Dựng consumer không thay đổi giữa hai bản

### 8.1. File `consumer/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.lab</groupId>
    <artifactId>sample-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <api.version>1.0.0</api.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.example.lab</groupId>
            <artifactId>sample-api</artifactId>
            <version>${api.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven property `api.version` cho phép đổi phiên bản dependency mà **không sửa file Java**. Đây là yêu cầu để phép thử source compatibility có giá trị.

### 8.2. File `consumer/src/main/java/com/example/consumer/CheckoutClient.java`

```java
package com.example.consumer;

import com.example.api.PriceCalculator;

public final class CheckoutClient {
    public static void main(String[] args) {
        PriceCalculator calculator = new PriceCalculator();

        // Được viết cho v1: total trả về int.
        int total = calculator.total(100, 20);

        // String implements cả CharSequence lẫn Serializable.
        String label = calculator.normalize("  item  ");

        // Public ở v1.
        calculator.flush();

        System.out.println(total + " / " + label);
    }
}
```

### 8.3. File `consumer/src/main/java/com/example/consumer/ExternalPaymentPlugin.java`

```java
package com.example.consumer;

import com.example.api.PaymentPlugin;

public final class ExternalPaymentPlugin implements PaymentPlugin {
    @Override
    public String name() {
        return "external";
    }
}
```

Consumer trên dùng những API của v1 theo các cách hợp lệ. Mục tiêu là **không chỉnh sửa source trong khi đối chứng**, kể cả khi đã biết v2 sẽ báo lỗi.

## 9. Build hai artifact và baseline consumer

Từ thư mục `api-comparison-lab`:

```bash
mvn -f api-v1/pom.xml clean install
mvn -f api-v2/pom.xml clean install
```

Hai JAR được tạo theo đường dẫn Maven mặc định:

```text
api-v1/target/sample-api-1.0.0.jar
api-v2/target/sample-api-2.0.0.jar
```

Mỗi bản được cài vào local Maven repository theo phiên bản riêng, không ghi đè lẫn nhau.

### 9.1. Compile consumer với v1

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile
```

Kết quả mong đợi: **BUILD SUCCESS**. Đoạn mã `CheckoutClient` và `ExternalPaymentPlugin` hợp lệ với API v1.

### 9.2. Lưu baseline để so sánh

Có thể lưu log hoặc artifact trong thư mục `reports` của bài thực hành:

```bash
mkdir -p reports

mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile > reports/consumer-v1-compile.log 2>&1
```

Ví dụ dùng redirection của Bash. Trong CI nên ghi thêm toolchain/JDK, commit, checksum JAR và dependency graph; một log compiler không đủ để chứng minh build dùng đúng candidate.

### 9.3. Không vội compile consumer với v2

Trước tiên hãy thu thập **API diff** từ hai JAR để dự đoán những lỗi có thể xuất hiện. Đó là ý nghĩa của việc dùng công cụ tự động làm bước đầu.

## 10. Kiểm tra class file bằng `javap`

`javap` có sẵn trong JDK, hữu ích khi chưa cài công cụ chuyên dụng hoặc khi cần xác minh một method descriptor gây lỗi.

### 10.1. Trích public API của v1

```bash
javap -classpath api-v1/target/sample-api-1.0.0.jar \
  -public -s \
  com.example.api.PriceCalculator \
  > reports/price-v1.txt
```

### 10.2. Trích public API của v2

```bash
javap -classpath api-v2/target/sample-api-2.0.0.jar \
  -public -s \
  com.example.api.PriceCalculator \
  > reports/price-v2.txt
```

### 10.3. So sánh output

```bash
diff -u reports/price-v1.txt reports/price-v2.txt
```

Đây là phép **so sánh văn bản tự động**. Trong output dự kiến sẽ thấy:

- `total(int,int)` đổi return type `int` → `long`.
- Method mới `normalize(java.io.Serializable)` xuất hiện.
- `flush()` không còn trong **public API view** của v2.

Để xác minh method `flush()` vẫn tồn tại nhưng không public, chạy:

```bash
javap -classpath api-v2/target/sample-api-2.0.0.jar \
  -p -s \
  com.example.api.PriceCalculator
```

`-p` yêu cầu hiển thị cả non-public members. Chú ý đây là **inspection**, không phải lời khuyên sử dụng API non-public trong consumer.

### 10.4. Kiểm tra interface

```bash
javap -classpath api-v1/target/sample-api-1.0.0.jar \
  -public com.example.api.PaymentPlugin

javap -classpath api-v2/target/sample-api-2.0.0.jar \
  -public com.example.api.PaymentPlugin
```

V2 thêm abstract method `audit()`. Kết quả này gợi ý cần kiểm tra những class của consumer triển khai interface.

### 10.5. Giới hạn của `javap + diff`

Phép so sánh text không có kiến thức đầy đủ để tự xác định:

- Method mới thêm có khiến overload resolution mơ hồ không?
- Một thay đổi trong generic signature phá source compatibility tới mức nào?
- Method trong subclass có được kế thừa/thay thế theo quy tắc JVM không?
- Interface change ảnh hưởng cụ thể consumer nào?
- Public type không còn accessible do JPMS?
- Class bên thứ ba có bị ảnh hưởng bởi transitive dependencies?

Vì vậy, `javap` là bước quan sát tốt nhưng **không thay thế** japicmp/Revapi hoặc consumer compilation tests.

## 11. So sánh API bằng japicmp

### 11.1. japicmp làm gì?

**japicmp** là công cụ so sánh hai phiên bản của một Java library ở mức JAR/class file, tập trung vào API differences và thông tin binary/source compatibility mà công cụ hỗ trợ.

Nó có thể phát hiện nhiều dạng thay đổi, chẳng hạn:

- Class/interface được thêm, xóa hoặc thay đổi.
- Method/constructor/field được thêm hoặc xóa.
- Thay đổi visibility/modifiers.
- Thay đổi return type hoặc parameter types.
- Thay đổi hierarchy/interface.
- Một số thay đổi liên quan generic signatures và các tương thích được công cụ phân loại.

Độ bao phủ cụ thể phụ thuộc phiên bản, options và phạm vi class được phân tích. Không mặc định mọi kết quả “compatible” là cam kết tuyệt đối cho mọi JDK/consumer.

### 11.2. Chuẩn bị CLI

Lấy **japicmp CLI artifact** từ kênh phát hành chính thức của dự án, chọn phiên bản có tài liệu hỗ trợ JDK của lab và xác nhận nó có thể chạy.

Trong hướng dẫn này, ký hiệu:

```text
/path/to/japicmp-CLI.jar
```

là đường dẫn tới JAR CLI có các dependency cần thiết của bản japicmp bạn chọn (một số release có distribution dạng “jar-with-dependencies”). Không dùng ký hiệu đó nguyên xi như một tên file thật.

Kiểm tra cách dùng bằng:

```bash
java -jar /path/to/japicmp-CLI.jar --help
```

### 11.3. Chạy so sánh hai JAR

```bash
java -jar /path/to/japicmp-CLI.jar \
  --old api-v1/target/sample-api-1.0.0.jar \
  --new api-v2/target/sample-api-2.0.0.jar
```

Nếu CLI của phiên bản được chọn có option `--only-modified`, có thể dùng để giảm nhiễu:

```bash
java -jar /path/to/japicmp-CLI.jar \
  --old api-v1/target/sample-api-1.0.0.jar \
  --new api-v2/target/sample-api-2.0.0.jar \
  --only-modified
```

Cú pháp và bộ options nên được đối chiếu với `--help` của **đúng release**. Không cần đoán tên một option ở phiên bản khác khi đang thiết lập CI.

### 11.4. Lưu báo cáo

```bash
java -jar /path/to/japicmp-CLI.jar \
  --old api-v1/target/sample-api-1.0.0.jar \
  --new api-v2/target/sample-api-2.0.0.jar \
  --only-modified \
  > reports/japicmp-api-diff.txt
```

Lệnh ví dụ lưu stdout. Nếu CLI cấu hình fail build bằng exit code khác 0 khi có incompatibility, shell/CI sẽ cần xử lý exit code đó theo policy; trong bài thực hành đang tạo breaking changes có chủ đích, một non-zero status có thể là kết quả **mong đợi của gate**, không phải lý do sửa công cụ.

### 11.5. Diễn giải báo cáo

Báo cáo dự kiến phản ánh:

| ID | Thay đổi được tạo | Ý nghĩa |
| --- | --- | --- |
| A1 | `total(int,int)` không còn chữ ký trả `int`, v2 có chữ ký trả `long`. | Binary client cũ có thể gọi descriptor không còn tồn tại. |
| A2 | `flush()` bị thu hẹp visibility. | Caller ngoài package không còn quyền như v1. |
| A3 | Thêm overload `normalize(Serializable)`. | Method cũ không bị xóa, nhưng source compilation cần kiểm tra riêng. |
| A4 | `PaymentPlugin` thêm abstract `audit()`. | Implementer bên ngoài cần xem xét. |
| A5 | Thay đổi implementation nhưng không thay API signature. | API diff có thể không phát hiện behavioral regression. |

**Không phải đây là output verbatim của một release japicmp cụ thể.** Cách hiển thị ký hiệu, mức độ severity và nhãn binary/source compatibility phụ thuộc công cụ và phiên bản. Khi làm bài, phải đọc **báo cáo thực tế**, gắn từng dòng với method/class trong JAR.

### 11.6. Lọc phạm vi và dependency

Nếu API JAR có nhiều package nội bộ, có thể cấu hình include/exclude filters theo khả năng tool để chỉ tập trung vào API được cam kết hỗ trợ.

Tuy nhiên, **lọc nhầm một package public** có thể che breaking change. Cần định nghĩa ranh giới API trước khi dùng filter. Ngoài ra, nếu class của API kế thừa hoặc tham chiếu một type ở dependency khác, công cụ có thể cần classpath bổ sung để phân tích chính xác. Không tùy tiện bật chế độ “ignore missing classes” rồi xem báo cáo là đầy đủ.

## 12. Kết quả nào là binary breaking change?

### 12.1. Đổi return type có thể đổi JVM descriptor

Bản v1:

```text
public int total(int, int)
descriptor: (II)I
```

Bản v2:

```text
public long total(int, int)
descriptor: (II)J
```

Consumer binary biên dịch với v1 sẽ tham chiếu descriptor cũ. Nếu runtime chỉ có v2, JVM có thể không tìm được method signature đó, dẫn đến `NoSuchMethodError`.

Chỉ nhìn source code thấy cùng tên `total` là không đủ. Đây là lý do một công cụ đọc class file hữu ích hơn việc so sánh tên method bằng grep.

### 12.2. Thu hẹp visibility

`public void flush()` ở v1 và package-private `void flush()` ở v2 là thay đổi khả năng truy cập. Consumer cũ ở package khác không còn được phép gọi method nếu chỉ có v2.

Khi compiler xử lý lại source với v2, thông báo thường liên quan member “not public” hoặc “cannot be accessed from outside package”. Với consumer binary cũ, có thể gặp `IllegalAccessError`.

### 12.3. Thêm abstract method vào interface

`PaymentPlugin` v2 thêm `audit()`. Một class consumer source implement v1 nhưng chưa có `audit()` có thể không còn biên dịch thành công với v2.

Về binary compatibility, hành vi của **thêm abstract method vào interface** cần phân biệt với source compatibility: class binary cũ có thể vẫn nạp được nhưng lời gọi tới method mới khi implementation không có có thể dẫn đến `AbstractMethodError`. Không nên đơn giản kết luận “thêm abstract method luôn giống xóa method”.

### 12.4. Thêm overload và binary compatibility

V2 giữ nguyên:

```java
public String normalize(CharSequence value)
```

và thêm:

```java
public String normalize(Serializable value)
```

Binary đã compile với v1 vẫn tham chiếu overload `normalize(CharSequence)`. Nó không tự chạy lại thuật toán overload resolution khi JVM gọi method.

Nhưng khi **recompile source** `normalize("  item  ")` với v2, compiler thấy String implements **cả `CharSequence` và `Serializable`**. Hai kiểu overload không có quan hệ subtype để chọn một bên cụ thể hơn, nên lời gọi có thể trở nên mơ hồ.

Đây là trường hợp minh họa rõ nhất vì sao **binary compatible không nhất thiết source compatible**.

## 13. Biên dịch lại consumer để tìm source compatibility break

### 13.1. Baseline v1

Nếu chưa chạy hoặc muốn chụp lại:

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile
```

Kết quả mong đợi: consumer source compile thành công.

### 13.2. Candidate v2

Giữ nguyên hai file Java của consumer, chỉ thay version dependency:

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=2.0.0 \
  clean compile
```

Lần compile này **được thiết kế để thất bại**. Những lỗi dự kiến có thể gồm:

1. `int total = calculator.total(...)`: `long` không tự gán vào `int`, lỗi incompatible types hoặc possible lossy conversion.
2. `calculator.normalize("  item  ")`: ambiguous overload.
3. `calculator.flush()`: method không còn public với caller ở package khác.
4. `ExternalPaymentPlugin`: class không implement abstract method `audit()` mới.

Tên/định dạng diagnostics phụ thuộc compiler và JDK, nhưng bản chất của các lỗi được xác định bởi Java type/access rules.

### 13.3. Diễn giải đúng kết quả

| v1 compile | v2 compile | Kết luận |
| --- | --- | --- |
| PASS | FAIL | Có regression source compatibility trong consumer và môi trường đã cố định. |
| PASS | PASS | Không phát hiện source break trong những source đã compile; chưa chứng minh toàn bộ hệ sinh thái. |
| FAIL | FAIL | Baseline không hợp lệ hoặc có blocker sẵn; không được quy mọi lỗi cho v2. |
| FAIL | PASS | Có thể candidate đã xử lý lỗi, nhưng phải giải thích vì sao baseline fail. |

**Không sửa consumer trước lần compile v2**. Nếu đã sửa code để gọi `(int) total`, ép kiểu cho normalize hoặc thêm `audit()`, đó là phép thử **migration readiness**, không còn là phép thử liệu v2 có giữ source compatibility với consumer cũ hay không.

### 13.4. Phân biệt source break và lỗi hạ tầng

Một lệnh Maven có exit code khác 0 không nhất thiết là API regression. Cần phân loại:

- Compiler diagnostic chỉ vào Java source/API: ứng viên source break.
- Dependency resolution failure: chưa tải được artifact đúng version.
- Plugin/JDK incompatibility: toolchain error.
- Annotation processor crash: processor compatibility.
- JDK class-file mismatch: dependency yêu cầu Java cao hơn.
- Repository authentication/network issue: lỗi môi trường.
- Test task bị skip: coverage không tương ứng với compile gate.

Khi muốn xác định nguyên nhân, dùng dependency tree hoặc effective POM để biết phiên bản thực được chọn.

## 14. Kiểm thử binary client cũ với library mới

### 14.1. Cần giữ binary đã compile ở v1

Sau khi biên dịch consumer thành công với v1, giữ lại folder output hoặc tạo JAR. Ví dụ:

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile
```

Kết quả có file:

```text
consumer/target/classes/com/example/consumer/CheckoutClient.class
```

**Chưa chạy lại `clean compile` với v2** khi muốn thử binary cũ; lệnh đó sẽ xóa hoặc thay output.

### 14.2. Chạy binary cũ với JAR v2

Với Bash/Unix, classpath separator là dấu `:`:

```bash
java -cp \
  consumer/target/classes:api-v2/target/sample-api-2.0.0.jar \
  com.example.consumer.CheckoutClient
```

Với Windows, dùng dấu `;` trong classpath, chẳng hạn:

```powershell
java -cp "consumer\target\classes;api-v2\target\sample-api-2.0.0.jar" com.example.consumer.CheckoutClient
```

Không cần chạy Maven dependency resolution ở bước này vì lab chỉ có một JAR API đơn giản.

Kết quả dự kiến: khi JVM đến lời gọi `total(int,int)`, binary cũ cần descriptor trả `int` nhưng JAR v2 chỉ cung cấp descriptor trả `long`. Lỗi tiêu biểu:

```text
java.lang.NoSuchMethodError: ...
```

Đó là bằng chứng **binary linkage** khác với lỗi compiler khi recompile source v2.

### 14.3. Vì sao cần một lượt runtime riêng?

Nếu bạn biên dịch lại consumer với v2, compiler có thể tạo descriptor tham chiếu mới. Khi chạy binary mới, một số linkage issue vốn chỉ xảy ra với binary cũ sẽ không còn.

Muốn phát hiện binary compatibility break, phải cố định **consumer class file được biên dịch theo v1**, sau đó thay JAR library ở runtime.

### 14.4. Giới hạn của smoke test

Một lần chạy `CheckoutClient` chỉ đi qua một số method. Nó không chứng minh toàn bộ binary contract. API comparison tool hỗ trợ phát hiện các thay đổi cấu trúc rộng hơn; integration tests tiếp tục xác nhận các đường gọi thực tế.

## 15. Sửa API để giữ tương thích theo lộ trình

### 15.1. Giữ method cũ, thêm method mới có tên khác

Nếu thư viện muốn mở rộng phép tính sang `long`, thay vì đổi return type tại chỗ có thể:

```java
public class PriceCalculator {
    @Deprecated
    public int total(int base, int tax) {
        return Math.addExact(base, tax);
    }

    public long totalLong(int base, int tax) {
        return (long) base + tax;
    }
}
```

`Math.addExact` trong ví dụ có thể ném `ArithmeticException` khi overflow. Nếu v1 dùng phép cộng `int` wraparound, đây là **thay đổi hành vi**, nên API compatibility cần đi cùng behavioral contract review.

Nếu mục tiêu là giữ đúng semantics v1, implementation của method cũ phải phản ánh contract đã cam kết; không tự ý đổi behavior chỉ để minh họa mở rộng kiểu.

### 15.2. Tránh overload có thể mơ hồ

Thay vì `normalize(Serializable)` cùng với `normalize(CharSequence)`, cân nhắc method có tên khác hoặc thiết kế API với hierarchy rõ:

```java
public String normalize(CharSequence text);
public String normalizeSerialized(Serializable value);
```

Đừng xem “chỉ thêm method” là chắc chắn source-compatible. Kiểm tra consumer corpus trước khi phát hành.

### 15.3. Giữ public method cũ nếu còn consumer

Nếu `flush()` đã công khai trong v1, thu hẹp visibility có thể phá cả source và binary client.

Có thể giữ phương thức public dưới dạng adapter/deprecated method trong cửa sổ tương thích và chuyển implementation nội bộ sang method riêng, sau khi có kế hoạch loại bỏ ở major release.

### 15.4. Thêm default method khi phù hợp

Nếu phải bổ sung chức năng cho `PaymentPlugin` nhưng chưa muốn buộc tất cả implementation cũ sửa code, một lựa chọn là default method:

```java
public interface PaymentPlugin {
    String name();

    default void audit() {
        // Default phải có semantics đúng và an toàn.
    }
}
```

Điều này có thể giữ nhiều source implementers compile. Tuy nhiên default method vẫn có rủi ro khi một class implement nhiều interface có method xung đột, hoặc khi default behavior không hợp nghiệp vụ. Recompile consumer và kiểm thử behavior vẫn cần thiết.

### 15.5. Breaking change có chủ đích

Đôi khi không cần duy trì source/binary compatibility (ví dụ major API rewrite với migration window rõ). Khi đó:

- Công cụ API diff vẫn cần chạy để phát hiện **toàn bộ thay đổi**.
- Báo cáo phải phân biệt break đã chấp nhận và break ngoài kế hoạch.
- Có migration guide và consumer owners.
- Có test chứng minh consumer **đã sửa** build/run đúng.
- Có versioning và release notes.
- Có kế hoạch rollback phù hợp với API/data changes.

Không tắt toàn bộ quality gate chỉ vì major version cho phép breaking changes.

## 16. Revapi và chiến lược so sánh mở rộng

### 16.1. Khi nào cân nhắc Revapi?

**Revapi** là một hệ sinh thái phân tích API changes có cơ chế extensions và filters. Nó thường phù hợp khi dự án muốn:

- So sánh API giữa các artifact/releases.
- Định nghĩa policy về những thay đổi được phép.
- Loại một số implementation details theo contract.
- Gắn report/check vào Maven build.
- Quản lý danh sách khác biệt đã chấp nhận với lý do.

Đối với một dự án có release policy nghiêm ngặt, đây có thể là lựa chọn bổ sung hoặc thay thế japicmp.

### 16.2. Điều cần cấu hình trước khi dùng

Với Revapi hoặc một API analyzer khác, phải xác định rõ:

1. Old artifact và new artifact: group/artifact/version/file/checksum.
2. Java API extension được dùng và phiên bản tương thích.
3. Public/protected API surface được cam kết.
4. Dependencies mà analyzer cần để đọc type hierarchy.
5. Filters loại code generated/internal nếu thực sự ngoài contract.
6. Severity/policy cho binary/source changes.
7. Cơ chế suppress/waiver có owner và lý do.
8. Output mà CI thu thập và cách fail gate.

Cú pháp plugin/extension thay đổi theo release; trong bài lab này không sao chép một cấu hình plugin giả định chưa được đối chiếu với version đã cài. Tài liệu chính thức và `help` của đúng release là nguồn để chốt tham số CI.

### 16.3. So sánh japicmp và Revapi

| Câu hỏi | japicmp | Revapi |
| --- | --- | --- |
| So sánh class/JAR Java trước–sau | Có, trọng tâm chính. | Có, qua Java API analysis extension. |
| Phân loại binary/API differences | Có. | Có, theo bộ extension/rules. |
| Tích hợp build/CI | CLI và plugin tùy cách triển khai. | Plugin/extensions cho build/policy. |
| Exclude/filters | Cần cấu hình theo công cụ. | Có cơ chế filters/transformations. |
| Kiểm tra business behavior | Không. | Không. |
| Chứng minh mọi consumer source compile | Không. | Không; phải recompile corpus. |

Không nên chọn công cụ chỉ theo số lượng nhãn “compatible/incompatible” trong output. Hãy ưu tiên tool phù hợp với Java baseline, API policy, hệ build và khả năng duy trì của nhóm.

## 17. API diff trong CI: từ báo cáo sang quality gate

### 17.1. Pipeline tối thiểu

```text
Build candidate library
         |
         v
Verify artifact identity / checksum
         |
         v
Compare old release JAR vs candidate JAR (japicmp/Revapi)
         |
         +------> Generate machine-readable/human-readable report
         |
         v
Check binary/source policy
         |
         v
Recompile representative consumer snapshots
         |
         v
Run old consumer binary against candidate
         |
         v
Integration / contract / runtime tests
         |
         v
Release decision + migration notes
```

Mỗi bước có phạm vi khác nhau. Nếu CLI report không phát hiện binary break, **vẫn phải chạy consumer compilation và behavior tests** theo cam kết của thư viện.

### 17.2. Chốt baseline bất biến

Một gate không đáng tin nếu `old` trỏ tới một SNAPSHOT được ghi đè, còn `new` trỏ tới source branch khác với artifact được publish.

Ghi:

```text
Library:
Old coordinate:
Old checksum:
New coordinate/file:
New checksum:
Source commit:
JDK:
Analyzer + version:
Analyzer config:
Consumer corpus revision:
Report location:
CI result:
```

Khi dùng Maven artifact repository, tốt nhất dùng release versions hoặc candidate artifacts có checksum/định danh bất biến.

### 17.3. Chạy CLI trong CI

Nếu bản japicmp bạn chọn hỗ trợ những options chặn binary incompatibility, có thể dùng chính sách như:

```bash
java -jar /path/to/japicmp-CLI.jar \
  --old api-v1/target/sample-api-1.0.0.jar \
  --new api-v2/target/sample-api-2.0.0.jar \
  --error-on-binary-incompatibility
```

**Xác nhận tên option bằng `--help` của phiên bản japicmp cụ thể trước khi đưa vào CI.** Một số bản tool hoặc plugin có tên option/configuration khác nhau.

Ở lab này có breaking changes cố ý nên quality gate binary compatibility **được kỳ vọng không pass**. Với thư viện production, điều đó sẽ chặn release trừ khi policy cho phép break hoặc có waiver được review.

### 17.4. Đừng tự động “fail mọi khác biệt”

Thêm public method đôi khi là thay đổi hợp lệ. Thay implementation nội bộ cũng có thể không đổi public API.

Chính sách có thể phân tầng:

- **Block:** loại bỏ/thu hẹp API công khai, thay descriptor không tương thích khi release cam kết ABI.
- **Review:** thêm overload, thay generic bounds, thêm abstract/default method, thay annotation contract.
- **Information:** API mới cộng thêm, deprecation có kế hoạch.
- **Separate gate:** behavior, serialization/schema, security và performance.

Không dựa vào một rule quá thô mà làm nhóm liên tục suppress cảnh báo để qua build.

### 17.5. Waiver cần có bằng chứng

Mẫu:

```text
Change ID: API-202
Type: Return type int -> long
Public symbol: com.example.api.PriceCalculator.total(int,int)
Detected by: japicmp
Affected consumers: checkout-service, invoice-batch
Decision: Breaking change accepted for major v2
Migration: Replace call with totalLong or adapt type
Owner: API team
Approval: Architecture/release owner
Expiry/review: Before next release line
Verification: Consumer recompilation + runtime test reports
```

Một waiver chỉ hợp lệ khi đúng symbol/change đã được đánh giá. Tránh tắt toàn bộ analyzer hoặc bỏ qua tất cả incompatibilities sau khi có một break được phê duyệt.

## 18. Thêm consumer recompilation vào CI

### 18.1. Consumer corpus

Nếu có nhiều project dùng thư viện, tạo danh sách các consumer đại diện:

- Consumer dùng public API thường xuyên.
- Consumer kế thừa/implement interfaces.
- Consumer có Java source level khác nhau.
- Consumer chạy trên classpath và module path.
- Consumer dùng annotation processor/codegen.
- Consumer quan trọng trong production.
- Consumer được build từ các ngôn ngữ JVM khác nếu thuộc phạm vi hỗ trợ.

Pin commit của từng consumer để giữ source cố định giữa baseline/candidate.

### 18.2. Hai lượt compile

Với một consumer Maven trong lab:

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile

mvn -f consumer/pom.xml \
  -Dapi.version=2.0.0 \
  clean compile
```

Lệnh thứ hai fail là tín hiệu đáng chú ý **chỉ khi lượt baseline đã pass trong cùng môi trường**.

Khi nhiều consumer chạy song song, cần tránh ghi đè output, local mutable snapshots và báo cáo của nhau. Dùng isolated workspace hoặc artifact repository ổn định khi cần.

### 18.3. Vì sao không sửa source trước khi đo?

Nếu ứng dụng được chuyển hết sang v2 và đã sửa các call sites, compiler success chỉ trả lời:

> “Consumer **sau khi migration** có compile với v2 không?”

Nó không trả lời:

> “API v2 có giữ tương thích với **consumer v1 chưa sửa** không?”

Hai kết quả đều hữu ích nhưng thuộc hai loại gate khác nhau.

### 18.4. Theo dõi phạm vi test

Nếu baseline corpus gồm 25 consumer mà job candidate chỉ compile 8 consumer, không được báo tất cả PASS.

Report nên có:

```text
planned_consumers
executed_consumers
baseline_pass
candidate_pass
source_break
environment_error
skipped_with_reason
skipped_unexpected
```

Một consumer bị skip vì không có credential hoặc artifact bị thiếu không phải consumer đã đạt compatibility.

## 19. Các trường hợp API diff cần xem kỹ hơn

### 19.1. Generics và type erasure

Ví dụ:

```java
// v1
public java.util.List<Number> values();

// v2
public java.util.List<Integer> values();
```

JVM descriptor của cả hai có thể vẫn có return type erasure là `java.util.List`, nhưng source:

```java
java.util.List<Number> result = api.values();
```

không còn hợp lệ với v2 vì `List<Integer>` không phải subtype của `List<Number>`.

Công cụ đọc generic signature có thể cảnh báo khác biệt, nhưng **recompile consumer là phép thử trực tiếp** cho trường hợp type inference/assignment cụ thể.

### 19.2. Checked exceptions

Ví dụ v1:

```java
public void save();
```

v2:

```java
public void save() throws java.io.IOException;
```

Thêm checked exception có thể phá source consumer nếu caller không catch hoặc không khai báo `throws`. JVM method descriptor không bao gồm danh sách checked exceptions theo cách compiler kiểm tra source.

Đây là ví dụ điển hình của sự khác biệt giữa **source-level contract** và **binary linkage**.

### 19.3. Method references và lambda

Khi thêm overload, một method reference như:

```java
java.util.function.Function<String, String> f =
        calculator::normalize;
```

có thể gặp quy tắc overload resolution/type inference khác so với một lời gọi trực tiếp. Phải thử với source consumer thực tế.

### 19.4. Inheritance và default methods

Nếu library thêm abstract method vào interface, class consumer chưa implement có thể fail khi recompile. Nếu thêm default method, có thể phát sinh xung đột giữa hai interface mà consumer implement.

Một API diff chỉ dựa vào “method added” không đủ để kết luận tất cả implementers đều an toàn.

### 19.5. Protected API

Library có thể cam kết cho phép subclass từ bên ngoài. Khi đó protected constructors và methods là một phần source/binary contract.

Không nên dùng API filter chỉ xem public methods của class mà bỏ toàn bộ protected members nếu dự án có extension/subclass consumers.

### 19.6. Public API lộ transitive dependency

Một method public có thể trả về type thuộc thư viện bên thứ ba:

```java
public com.vendor.json.Document parse(String source);
```

Nếu dependency ấy đổi major version hoặc bị relocate, consumer có thể chịu breaking change dù tên method trong thư viện chính không đổi.

Hãy ghi API types của transitive dependencies, so effective dependency graph và kiểm tra published POM/module metadata.

## 20. Module system (JPMS) cũng là một phần compatibility

### 20.1. `exports` và Java source

Một JAR modular có:

```java
module com.example.api {
    exports com.example.api;
}
```

Nếu v2 bỏ export hoặc đổi module name, source consumer có thể compile fail khi dùng module path, dù `.class` vẫn tồn tại trong JAR.

Để so sánh đúng, ngoài class-level API diff cần kiểm tra `module-info.class` và module descriptor.

### 20.2. Kiểm tra descriptor

```bash
jar --describe-module \
  --file api-v1/target/sample-api-1.0.0.jar

jar --describe-module \
  --file api-v2/target/sample-api-2.0.0.jar
```

Trong **lab hiện tại**, hai JAR không chứa `module-info.class`, nên kết quả có thể là thông tin automatic module nếu được đặt trên module path. Đừng coi đó là một explicit module descriptor đã được thiết kế.

### 20.3. Ordinary access và deep reflection

- `exports` kiểm soát khả năng truy cập public types/members từ các module thích hợp.
- `opens` cho phép deep reflection vào package theo policy.
- `--add-exports` và `--add-opens` là những override phục vụ các trường hợp cụ thể.

API comparison dựa trên public/protected class signatures có thể không phát hiện rằng một framework serializer ở runtime sẽ ném `InaccessibleObjectException` vì module đích không open package.

Nếu phát hành modular library, bổ sung test reflection/framework thực sự, không chỉ source compile.

### 20.4. Multi-release JAR

Một thư viện có thể chứa:

```text
com/example/api/PriceCalculator.class
META-INF/versions/17/com/example/api/PriceCalculator.class
META-INF/versions/21/com/example/api/PriceCalculator.class
```

Các JDK khác nhau có thể dùng class variant khác nhau. Khi so sánh API, cần xác định công cụ có hiểu multi-release JAR hay không và đang dùng view nào của artifact.

Nếu sản phẩm cam kết chạy trên Java 11, 17 và 21, không được kết luận tương thích chỉ từ phân tích root entry hoặc một JDK duy nhất. Hãy chọn tool/matrix phù hợp và compile/run consumer ở các JDK được hỗ trợ.

## 21. Serialization, SPI và reflection nằm ngoài diff chữ ký

### 21.1. Java serialization

Thư viện có thể giữ chữ ký public method nhưng đổi tên class, `serialVersionUID` hoặc cấu trúc object được serialize. Dữ liệu được lưu từ v1 có thể không đọc được bằng v2.

Cần migration test với **serialized fixtures thực từ v1**, không chỉ đối chiếu method signatures.

### 21.2. `META-INF/services` và `ServiceLoader`

Một service provider có thể được đăng ký qua file:

```text
META-INF/services/com.example.spi.Provider
```

Nếu JAR mới thiếu resource hoặc provider name sai, `ServiceLoader` không tìm thấy implementation. Công cụ API diff class-level có thể không báo, vì `.class` vẫn tồn tại.

Khi shading/relocation dependency trong migration, hãy kiểm tra metadata service và chạy test thật qua `ServiceLoader.load(...)`.

### 21.3. Reflection theo tên class

Ví dụ:

```java
Class<?> type = Class.forName(configuredProviderClass);
```

Tên class có thể nằm trong properties, YAML, XML, DB hoặc environment. Nếu package đổi tên, việc compile source có thể vẫn thành công nhưng runtime báo `ClassNotFoundException`.

Cần có resource/configuration compatibility tests và danh sách aliases/migration rõ.

### 21.4. Wire schemas

JSON/Avro/Protobuf/HTTP contracts không được xác minh đầy đủ bằng Java API diff. Nếu một Java DTO dùng cùng public getters nhưng serialization config đổi tên property, client vẫn có thể bị hỏng.

Sử dụng schema diff, consumer-driven contracts và golden payload fixtures theo hệ thống thực.

## 22. So sánh API khi nâng JDK hoặc framework

### 22.1. Tách thay đổi thư viện khỏi thay đổi compiler

Để xác định API break do thư viện:

```text
Consumer source S cố định
Compiler/JDK E cố định
Lib v1 -> compile
Lib v2 -> compile
```

Để xác định tác động JDK:

```text
Consumer source S cố định
Lib version L cố định ở tổ hợp được hỗ trợ
JDK cũ -> compile
JDK mới -> compile
```

Sau đó mới chạy tổ hợp cuối cùng `JDK mới + lib mới`. Nếu đổi JDK, compiler, BOM và library cùng lúc, lỗi compiler có thể không truy nguyên được.

### 22.2. `--release` và minimum Java version

Ví dụ:

```bash
javac --release 17 \
  -cp api-v2/target/sample-api-2.0.0.jar \
  -d out \
  path/to/Consumer.java
```

`--release` giúp giới hạn source/target và Java SE APIs khi compile. Nó **không tự bảo đảm** mọi dependency bên thứ ba chạy được trên runtime Java 17.

Trong CI, ghi đồng thời JDK chạy compiler, Java release target, JDK chạy test và Java runtime ở production.

### 22.3. Jakarta EE namespace change

Một framework major upgrade có thể đổi source API từ `javax.persistence`/`javax.servlet` sang `jakarta.persistence`/`jakarta.servlet`. Đây là một thay đổi Java API ecosystem và dependency, nên API diff và recompilation tests có giá trị.

Nhưng **không thay mọi `javax.*` thành `jakarta.*`**; các package Java SE như `javax.sql` vẫn giữ tên. Cần theo đúng migration guide của framework và version target.

### 22.4. Binary client trước khi nâng

Một ứng dụng được compile bằng Java 11 có thể chạy trên JVM mới nếu bytecode/dependency tương thích, nhưng không được đảm bảo trong mọi trường hợp do các API bị xóa, internal access, class loaders và framework changes.

Dùng API diff để đánh giá dependency version, sau đó thử binary cũ trên runtime mới và đọc các lỗi như:

```text
NoSuchMethodError
NoClassDefFoundError
IllegalAccessError
IncompatibleClassChangeError
UnsupportedClassVersionError
```

Không gán tất cả các lỗi trên cho một nguyên nhân. Chúng có thể phản ánh classpath, API changes, visibility hoặc JVM version khác nhau.

## 23. Mẫu báo cáo API comparison

Một báo cáo tốt không chỉ ghi “breaking: yes/no”. Nó nên gắn thay đổi với consumer và hành động cụ thể:

| ID | API symbol | Thay đổi | Nhóm rủi ro | Consumer ảnh hưởng | Quyết định |
| --- | --- | --- | --- | --- | --- |
| API-01 | `PriceCalculator.total(int,int)` | Return `int` → `long` | Binary/source break | Checkout | Giữ adapter hoặc major migration. |
| API-02 | `PriceCalculator.flush()` | Public → package-private | Binary/source access break | Checkout | Giữ public contract hoặc cập nhật client. |
| API-03 | `normalize(Serializable)` | Added overload | Source ambiguity risk | Checkout | Đổi tên API hoặc sửa overload. |
| API-04 | `PaymentPlugin.audit()` | Added abstract method | Implementer source break | External plugins | Default method hoặc migration guide. |
| API-05 | Behavior `total` | Logic thay đổi nếu có | Behavioral | Billing consumers | Regression tests riêng. |

Thêm các trường quản trị:

```text
Library coordinates:
Old version/checksum:
New version/checksum:
JDK/compiler:
Analyzer + version:
Analyzer configuration:
Build/dependency resolution:
Consumer corpus:
Report artifact:
Decision/owner:
Waiver/migration ticket:
Verification evidence:
```

### 23.1. Phân loại severity

- **Blocker:** breaking change ngoài kế hoạch đối với API cam kết binary compatibility, hoặc consumer quan trọng không compile.
- **High:** breaking change được dự kiến nhưng chưa có migration path cho consumers quan trọng.
- **Medium:** thay đổi có thể sửa cơ học và có kế hoạch rõ.
- **Info:** API bổ sung, deprecation, thay đổi được ghi nhận nhưng không phá contract trong phạm vi xác định.

Severity phụ thuộc **chính sách phát hành và mức độ sử dụng API**, không chỉ ký hiệu của một tool.

### 23.2. Mức độ tin cậy của kết luận

Dùng ngôn ngữ chính xác:

- “Không phát hiện binary incompatibility trong phạm vi JAR được analyzer kiểm tra.”
- “Consumer corpus 12/12 compile thành công trên JDK 17 với API v2.”
- “Consumer binary cũ chạy qua 5 integration scenarios.”
- “Không có dữ liệu xác minh external plugin consumers.”
- “Serialization compatibility chưa được kiểm thử.”

Không viết “thư viện tương thích hoàn toàn” khi mới chỉ có một báo cáo japicmp.

## 24. Những lỗi thường gặp khi dùng công cụ API diff

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Báo cáo rỗng dù source đổi | Chỉ đổi implementation/private code hoặc so nhầm JAR. | Xác minh checksum, `jar tf` và class signatures. |
| Báo cáo rỗng nhưng consumer compile fail | Overload/generics/processor/JPMS không được rule phát hiện. | Recompile consumer; xem compiler diagnostics. |
| API diff báo class removed | Class bị relocate/shaded hoặc artifact thiếu entry. | So FQCN, packaging và include/exclude filters. |
| Analyzer lỗi missing class | Thiếu dependency classpath/type hierarchy. | Cung cấp dependencies phù hợp, không mặc định ignore. |
| Kết quả thay đổi giữa CI jobs | SNAPSHOT mutable, dependency cache hoặc JDK/tool version khác. | Pin artifact và toolchain/checksum. |
| Binary diff pass nhưng runtime `NoSuchMethodError` | Runtime nạp JAR khác hoặc công cụ bỏ qua một API. | In class origin, dependency graph và `javap`. |
| Consumer compile fail trên JDK mới | JDK/toolchain/release không tương thích. | Thử matrix tách JDK và library. |
| CI báo PASS nhưng chỉ chạy ít consumer | Jobs bị skip hoặc corpus không được tải đủ. | Theo dõi planned/executed counts. |
| API report quá nhiều internal changes | Filter chưa phản ánh API policy. | Phân loại packages, giữ protected/public API thật. |
| Suppress làm mất breaking changes mới | Waiver quá rộng hoặc không có expiry. | Thu hẹp theo symbol/change và review. |
| JAR có cùng version nhưng khác nội dung | SNAPSHOT/local install bị ghi đè. | Dùng immutable coordinates/checksums. |
| V2 source compile nhưng client cũ lỗi | Recompile tạo bytecode mới, binary cũ vẫn không phù hợp. | Chạy binary client được compile với v1. |

## 25. Bài tập mở rộng

### Bài tập 1: thay đổi generics

Thay một API từ:

```java
public java.util.List<Number> values();
```

sang:

```java
public java.util.List<Integer> values();
```

Sau đó:

1. Dùng `javap -s` để xem descriptor ở cả hai bản.
2. Dùng japicmp kiểm tra khác biệt ở generic signature nếu công cụ hỗ trợ.
3. Tạo consumer gán kết quả vào `List<Number>`.
4. Compile baseline/candidate và ghi kết quả.
5. Giải thích vì sao erasure có thể khiến binary compatibility khác source compatibility.

### Bài tập 2: thay checked exception

V1:

```java
public void send();
```

V2:

```java
public void send() throws java.io.IOException;
```

Compile một consumer có method `process()` không catch hoặc declare `IOException`. So sánh kết quả API diff và compiler. Nêu vì sao checked exception thuộc source contract dù không làm thay JVM method descriptor như parameter/return type.

### Bài tập 3: thử API module descriptor

Tạo một modular library có:

```java
module com.example.lab.api {
    exports com.example.api;
}
```

V2 bỏ export `com.example.api`. Dùng `jar --describe-module` để thấy thay đổi và compile consumer named module. Quan sát rằng class có thể còn trong JAR nhưng source consumer không còn nhìn thấy package.

### Bài tập 4: thêm public method nhưng không phá source

Thêm method khác tên và không ảnh hưởng overload resolution. Quan sát japicmp ghi API mới, trong khi consumer v1/v2 vẫn compile. Giải thích vì sao quality gate không nên chặn mọi thay đổi được phát hiện.

### Bài tập 5: behavior thay đổi, chữ ký giữ nguyên

Giữ `total(int,int)` nhưng thay cách xử lý overflow hoặc giá trị âm. Chạy API diff rồi tạo regression tests với input biên. Kết luận tại sao API comparison không thay thế behavioral testing.

### Bài tập 6: tạo policy cho thư viện thật

Chọn một thư viện dùng trong hệ thống (với các phiên bản được hỗ trợ và có quyền kiểm thử). Xác định:

- Tập public API cam kết.
- Old/candidate coordinates.
- API analyzer và tool version.
- Consumer corpus.
- Ngưỡng chặn binary/source breaks.
- Quy trình waiver.
- Test/report artifact lưu trong CI.

Không ép mọi internal implementation detail thành API contract nếu nhóm không có cam kết duy trì nó.

## 26. Tiêu chí hoàn thành bài thực hành

Một bài thực hành đạt mục tiêu khi có những **bằng chứng kỹ thuật** sau:

- Hai JAR v1/v2 build từ source rõ ràng và có version/checksum phân biệt.
- `javap` thể hiện return descriptor và visibility thay đổi.
- japicmp hoặc công cụ tương đương tạo API differences từ hai JAR.
- Người học chỉ ra được A1/A2/A3/A4 là các loại rủi ro khác nhau.
- Consumer source giữ nguyên compile PASS với v1 và FAIL với v2 theo các lỗi được thiết kế.
- Binary client được compile với v1 rồi chạy với v2 để quan sát linkage break.
- Có ít nhất một giải pháp giữ tương thích hoặc một migration plan có chủ đích.
- Báo cáo ghi rõ giới hạn: chưa tự chứng minh reflection, serialization và behavior.
- Có đề xuất CI gate không bỏ qua consumer bị skip hoặc artifact mutable.

Lưu ý: những tiêu chí này là **yêu cầu của người học trong bài lab**, không thay thế quy trình Content QA riêng đối với tài liệu.

## 27. Checklist áp dụng vào dự án thực

### Trước khi chạy

- [ ] Xác định thư viện, phiên bản cũ/mới và cam kết source/binary compatibility.
- [ ] Khóa artifact tọa độ/checksum, compiler/JDK và dependency versions.
- [ ] Xác định public/protected API surface và các package không cam kết.
- [ ] Chọn API analyzer hỗ trợ class-file level của JDK đích.
- [ ] Tập hợp consumer corpus và source snapshots ở commit xác định.
- [ ] Kiểm tra Maven/Gradle profiles, modules, annotation processors và generated source.

### Khi so sánh

- [ ] Chạy analyzer trên đúng hai artifact, lưu stdout/report.
- [ ] Đọc `javap -s` với những method có binary descriptor khác.
- [ ] Kiểm tra changes ở inheritance, interface, generics và overloads.
- [ ] Compile consumer với v1 để chốt baseline PASS.
- [ ] Compile cùng source với v2 trên cùng môi trường.
- [ ] Phân loại lỗi compiler khác lỗi repository/toolchain.
- [ ] Chạy binary consumer cũ với library mới khi ABI là cam kết.
- [ ] Kiểm tra module descriptor nếu dùng JPMS.
- [ ] Kiểm tra reflection/SPI/serialization/configuration nếu có.

### Trước khi phát hành

- [ ] Gắn mỗi breaking change với consumer ảnh hưởng, owner và quyết định.
- [ ] Có adapter/deprecation plan hoặc migration guide cho breaks được chấp nhận.
- [ ] Có regression/contract tests cho thay đổi hành vi.
- [ ] Có report artifacts trong CI và phạm vi consumer thực sự được chạy.
- [ ] Không có waiver quá rộng che thay đổi mới.
- [ ] Đã xác minh artifact được kiểm thử là artifact sẽ phát hành.
- [ ] Đã cập nhật release notes và support/migration policy.

## 28. Kết luận

**So sánh API trước và sau thay đổi bằng công cụ tự động** là một bước quan trọng của Java Advance Compatibility Migration, vì nó chuyển những khác biệt trong mã thư viện thành báo cáo có cấu trúc về class, method, field và compatibility risks. Trong bài lab, `javap` cho thấy chữ ký JVM, japicmp giúp nhận diện API changes, consumer recompilation bắt những source breaks như overload ambiguity, còn runtime test với binary cũ bộc lộ linkage break.

Nguyên tắc then chốt là **mỗi công cụ trả lời một câu hỏi giới hạn**. API diff không thay cho kiểm thử source consumer; source compile không bảo đảm binary cũ chạy; binary linking không chứng minh semantics không đổi. Khi kết hợp đúng các lớp kiểm chứng, khóa artifact/toolchain và đưa chính sách vào CI, nhóm phát triển có thể nâng JDK, framework và thư viện dùng chung mà vẫn nhìn thấy sớm những thay đổi phá vỡ hợp đồng với consumer.
