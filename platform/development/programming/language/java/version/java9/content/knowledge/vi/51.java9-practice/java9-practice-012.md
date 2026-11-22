# Kiểm thử locale, XML, JDBC cùng dữ liệu ngoài hợp đồng (Java 17+)

## 1. Mục tiêu: kiểm tra hợp đồng dữ liệu qua nhiều ranh giới

Một hệ thống Java có thể nhận đồng thời **mã locale** từ request, **XML** từ đối tác và dữ liệu nghiệp vụ lưu bằng **JDBC**. Lỗi không chỉ xảy ra khi một chuỗi sai cú pháp: dữ liệu có thể **hợp lệ về cú pháp nhưng không thuộc tập mà ứng dụng cam kết hỗ trợ**, hoặc đi qua lớp parsing rồi làm thay đổi trạng thái cơ sở dữ liệu ngoài dự kiến.

Bài thực hành này kiểm tra ba ranh giới liên kết:

1. **Locale (BCP 47):** tag phải đúng cú pháp, thuộc danh sách locale được hỗ trợ; không tự rơi về default locale.
2. **XML (JAXP/DOM):** tài liệu phải well-formed, đúng cấu trúc nghiệp vụ, không tải DTD/entity bên ngoài, không chấp nhận số lượng sai.
3. **JDBC:** giá trị nghiệp vụ phải đạt điều kiện; câu SQL sử dụng tham số hóa; ràng buộc database bảo vệ cả đường ghi không qua ứng dụng; giao dịch phải rollback khi cả lô không hợp lệ.

> **“Dữ liệu ngoài hợp đồng”** ở đây là dữ liệu **không đáp ứng yêu cầu đầu vào đã xác định**, kể cả khi cú pháp của nó tự thân vẫn đúng. Mỗi ranh giới phải có kết quả rõ: chấp nhận + xử lý đúng, từ chối có kiểm soát, hay lỗi cấu hình; không được sửa ngầm dữ liệu rồi giả vờ hợp lệ.

**Mối liên hệ với Java 9:** Java 9 có các API chuẩn Java SE cần thiết như `Locale.Builder`, JAXP, JDBC và module system. Bài chọn **Java 17+**, **JUnit Jupiter 6** và **H2 2.5** để dùng stack hiện hành; những công cụ kiểm thử là thư viện phụ thuộc, **không được tích hợp sẵn vào JDK**. Không sử dụng API Java đã bị loại bỏ hay phương thức parser không an toàn làm mặc định.

## 2. Xác định hợp đồng trước khi viết test

Giả sử endpoint nhập một đơn hàng với ba giá trị:

```text
languageTag = "vi-VN"
xml         = "<order qty=\"3\"/>"
sku         = "BOOK_17"
```

Ứng dụng phải xử lý theo thứ tự **locale → XML → JDBC**, với hợp đồng ví dụ:

| Ranh giới | Đầu vào được chấp nhận | Ngoài hợp đồng phải từ chối |
| --- | --- | --- |
| Locale | Một trong `vi-VN`, `en-US` (không phân biệt chữ hoa/thường của tag BCP 47 nếu parser chuẩn hóa) | `null`, rỗng, `en_US`, tag hợp lệ `xx-ZZ` nhưng không được hỗ trợ, độ dài vượt giới hạn |
| XML | Đúng một root `<order qty="N"/>`, không namespace, không thuộc tính khác, `N` nguyên từ `1` tới `1000` | Không well-formed, root khác, phần tử con, số âm/zero/vượt giới hạn, XML có `DOCTYPE` và external entity |
| JDBC | `sku` khớp `[A-Z0-9_-]{1,20}`, quantity trong `[1,1000]` | SKU/quantity sai điều kiện, vi phạm `NOT NULL`/`UNIQUE`/`CHECK`; SQL injection không được sửa cú pháp truy vấn |
| Batch | Mọi bản ghi trong một giao dịch phải hợp lệ thì mới `commit` | Nếu một bản ghi sai, `rollback` toàn bộ lô; không để lại bản ghi nửa chừng |

Các con số/locale trong bảng là **giả định nghiệp vụ dành cho bài tập**, không phải giới hạn mặc định của Java hay của chuẩn XML/JDBC. Khi áp dụng thực tế, đổi đúng theo tài liệu API, schema, quy định dữ liệu và chính sách tổ chức; tránh dùng một whitelist mẫu cho tất cả sản phẩm.

### Bốn tầng xác minh

- **Unit/contract test:** kiểm tra parsing, validation, normalization và thông báo lỗi trong lớp ứng dụng.
- **Security negative test:** đưa payload đối nghịch như XXE và chuỗi SQL injection, xác nhận bị từ chối hoặc được xử lý như dữ liệu.
- **Integration test:** sử dụng JDBC driver và database thật trong test, kiểm tra constraint, transaction, rollback và đường nhập liên kết.
- **Environment/compatibility test:** chạy thêm với DB engine/driver giống production, JDK được hỗ trợ, locale/encoding và JAXP provider của môi trường triển khai. H2 chỉ là một bước kiểm thử tích hợp, không chứng minh tính tương thích với PostgreSQL, MySQL hoặc Oracle.

## 3. Kiểm thử locale: cú pháp BCP 47 khác với “được hỗ trợ”

### 3.1. Nên parse nghiêm ngặt khi kiểm tra hợp đồng

API `Locale.forLanguageTag(String)` hữu ích để đọc BCP 47 nhưng **có tính lenient**: phần không hợp lệ và các phần theo sau có thể bị bỏ qua. Với đầu vào mà hệ thống yêu cầu **phải đúng cú pháp**, dùng:

```java
Locale locale = new Locale.Builder()
    .setLanguageTag(languageTag)
    .build();
```

`Locale.Builder.setLanguageTag` kiểm tra cú pháp và ném `IllformedLocaleException` khi tag không well-formed. Đừng quên kiểm tra rỗng/`null` riêng vì builder có thể xử lý chuỗi rỗng như thao tác reset; parser đúng cú pháp **chưa chứng minh locale là một lựa chọn được ứng dụng hỗ trợ**.

Ví dụ:

| Tag | Cú pháp | Chính sách hai locale của bài | Kỳ vọng |
| --- | --- | --- | --- |
| `vi-VN` | Hợp lệ | Có | Nhận |
| `en-us` | Hợp lệ, chuẩn hóa thành `en-US` | Có | Nhận |
| `en_US` | Không đúng dạng BCP 47 yêu cầu | Không | `IllformedLocaleException` |
| `xx-ZZ` | Có thể hợp lệ về cú pháp | Không | `IllegalArgumentException` do whitelist |
| `""`, `null` | Không đáp ứng hợp đồng | Không | `IllegalArgumentException` có kiểm soát |

**Không kiểm thử “Locale.VIETNAM luôn có mặt” bằng cách so một mảng `Locale.getAvailableLocales()` cố định.** Dữ liệu CLDR, bản JDK và provider có thể thay đổi. Nếu nghiệp vụ cần định dạng số/ngày, dùng `NumberFormat`, `DateTimeFormatter` với locale xác định rồi kiểm tra bất biến có ý nghĩa; đừng mặc định dấu phân cách luôn giống nhau giữa mọi bản CLDR.

### 3.2. Không dùng default locale toàn JVM cho test song song

`Locale.setDefault(...)` tác động đến trạng thái toàn process, có thể khiến test nhiễu nhau. Ưu tiên truyền đối tượng `Locale` vào formatter hoặc service. Khi buộc phải kiểm thử default locale, phải lưu/khôi phục trong `try/finally`, tránh chạy song song với các test khác tác động locale. Mục tiêu là **test độc lập với cấu hình vùng của máy CI**.

## 4. Kiểm thử XML: phân biệt cú pháp, schema và an toàn parser

Một XML có thể well-formed nhưng vẫn sai hợp đồng:

```xml
<order qty="0"/>
```

XML trên đúng cú pháp, nhưng `qty=0` không đáp ứng miền giá trị `1..1000`. Ngược lại, XML thiếu thẻ đóng không well-formed. Đặc biệt, XML chứa `DOCTYPE`/external entity có thể gây **XXE, truy cập file, SSRF hoặc denial-of-service** nếu parser bị cấu hình sai.

### 4.1. Cấu hình DOM fail closed

Với JAXP hiện hành, bài thực hành đặt đồng thời:

```java
DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
f.setNamespaceAware(true);
f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
f.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl",
    true
);
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
f.setXIncludeAware(false);
f.setExpandEntityReferences(false);
```

Phần lớn cấu hình trên là API chuẩn, còn feature URI `disallow-doctype-decl` phụ thuộc khả năng parser nhưng được JAXP JDK hiện đại khuyến nghị. **Nếu provider không nhận thuộc tính/feature bảo vệ, phải thất bại ngay khi khởi tạo**, không bắt lỗi rồi tiếp tục với parser không an toàn. `FEATURE_SECURE_PROCESSING` giúp giới hạn tài nguyên nhưng **không phải giải pháp XXE duy nhất**; `setExpandEntityReferences(false)` không thay thế quyền truy cập tài nguyên bên ngoài hay lệnh cấm DTD.

**Lưu ý về giới hạn kích thước:** bài demo hạn chế số ký tự trong `String` trước khi parse; với XML nhận từ HTTP/file, **phải giới hạn byte trước khi đọc hết vào RAM**, ngoài timeout và giới hạn cấu trúc/nesting. Không cho phép payload quá lớn chỉ vì nó là XML well-formed.

### 4.2. Ma trận XML nên kiểm thử

| Trường hợp | Input mẫu | Kết quả |
| --- | --- | --- |
| Happy path | `<order qty="3"/>` | Parse thành quantity 3 |
| Thiếu thuộc tính bắt buộc | `<order/>` | Từ chối |
| Sai miền giá trị | `<order qty="0"/>`, `<order qty="1001"/>` | Từ chối |
| Sai kiểu | `<order qty="abc"/>` | Từ chối |
| Thừa trường | `<order qty="2" discount="5"/>` | Từ chối theo contract strict |
| Thừa phần tử | `<order qty="2"><extra/></order>` | Từ chối |
| Sai root/namespace | `<request qty="2"/>`, root có namespace khác | Từ chối |
| Sai cấu trúc XML | `<order qty="1">` thiếu thẻ đóng | Ném `SAXException` |
| DOCTYPE/XXE | `<!DOCTYPE order [... ENTITY ...]>` | Ném `SAXException` **trước khi đọc tài nguyên ngoài** |
| Null/rỗng/vượt giới hạn | `null`, `""`, String dài | Từ chối ở ranh giới input |

**Well-formed XML ≠ XML hợp schema ≠ XML an toàn.** Nếu sản phẩm dùng XSD, phải bổ sung schema validation bằng `SchemaFactory`/`Validator` với ràng buộc external access và catalog/resolver đã kiểm chứng. Demo dùng kiểm tra cấu trúc cực nhỏ để dễ hiểu, **không giả làm XSD validator tổng quát**.

## 5. Kiểm thử JDBC: cả service lẫn database đều bảo vệ dữ liệu

Không chỉ kiểm thử rằng `INSERT` thành công. Cần ba lớp bảo vệ:

1. **Validation trước JDBC:** từ chối dữ liệu ngoài miền nghiệp vụ (`sku` sai quy tắc, `qty` không hợp lệ) trước khi gọi SQL.
2. **PreparedStatement:** giá trị đưa vào bằng `?` và `setString`/`setInt` để dữ liệu người dùng **không trở thành SQL syntax**.
3. **Database constraint:** `PRIMARY KEY`/`UNIQUE`/`NOT NULL`/`CHECK` phải chặn các đường ghi bỏ qua lớp service, race condition và bug.

### 5.1. SQL injection cần kiểm tra đúng đối tượng

**Sai** vì nối giá trị vào SQL:

```java
String sql = "SELECT qty FROM orders WHERE sku = '" + userSku + "'";
```

**Đúng** vì bind tham số:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT qty FROM orders WHERE sku = ?")) {
    ps.setString(1, userSku);
    try (ResultSet rs = ps.executeQuery()) {
        // Xử lý kết quả
    }
}
```

Một chuỗi như `A1' OR '1'='1` phải được coi là **giá trị nguyên văn của một tham số**. Truy vấn không được trả dữ liệu của `A1` chỉ vì chuỗi đầu vào cố tạo điều kiện SQL. Tuy nhiên, `PreparedStatement` không tự bảo vệ **tên bảng, tên cột, ORDER BY hoặc toàn bộ câu SQL dựng từ input**: những thành phần cấu trúc phải dùng allowlist và câu lệnh cố định.

### 5.2. Test transaction phải kiểm tra cả trạng thái sau lỗi

Khi một lô có ba bản ghi, bản ghi thứ hai vi phạm hợp đồng thì test phải xác minh:

- Dòng thứ nhất **chưa trở thành dữ liệu bền vững** nếu giao dịch bị rollback.
- Không có dữ liệu bị ghi một phần khi test ném ngoại lệ.
- `setAutoCommit(false)` được đặt đúng trước khi thực hiện cả lô; `rollback()` chạy khi bất kỳ bước nào thất bại; `commit()` chỉ chạy sau khi mọi bước hoàn tất.
- Test không phụ thuộc DB test khác đã ghi dữ liệu trước đó.

Demo sử dụng **H2 in-memory** do driver JDBC riêng cung cấp; H2 giúp kiểm tra đường đi SQL, binding, schema và transaction một cách nhanh. Để chứng minh các hành vi đặc thù của một sản phẩm DB, chạy thêm suite trên DB/version/driver production (ví dụ qua container được quản lý đúng).

## 6. Dự án test Java 17+ dùng Maven, JUnit Jupiter và H2 hiện hành

Bộ ví dụ hoàn chỉnh gồm **3 file**:

```text
contract-tests/
├── pom.xml
└── src/
    ├── main/java/demo/BoundaryContracts.java
    └── test/java/demo/BoundaryContractsTest.java
```

Yêu cầu máy: **JDK 17+**, **Maven 3.9+** và quyền tải dependency từ kho tin cậy. Các phiên bản phụ thuộc minh họa được chốt để có thể tái lập: **JUnit Jupiter 6.1.3** (yêu cầu Java 17+), **H2 2.5.252**, **Maven Compiler Plugin 3.16.0**, **Surefire 3.6.1**. Khi áp dụng vào dự án thực tế, cập nhật theo policy dependency của tổ chức và chạy lại bộ test; tránh dùng dependency `LATEST`/`RELEASE` không có khả năng tái lập.

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>contract-tests</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>6.1.3</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.5.252</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

H2 có scope `test` vì **`BoundaryContracts` chỉ sử dụng giao diện `java.sql` chuẩn**: main source không import class `org.h2.*`. Driver H2 được nạp thông qua classpath service của JDBC khi chạy test. Đây cũng là nguyên tắc phù hợp với chương trình chính dùng driver khác trong production.

## 7. Mã ứng dụng: `src/main/java/demo/BoundaryContracts.java`

Đây là **lớp thư viện hoàn chỉnh**, không có `main()` riêng: test JUnit bên dưới gọi trực tiếp các phương thức. Nó không cần JUnit/H2 khi biên dịch mã nguồn chính.

```java
package demo;

import java.io.StringReader;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Locale;
import java.util.Set;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class BoundaryContracts {
    private static final Set<String> SUPPORTED_LANGUAGES =
        Set.of("vi-VN", "en-US");

    private BoundaryContracts() {}

    // Hợp đồng: tag đúng cú pháp BCP 47, không rỗng,
    // nằm trong hai locale mà sản phẩm đã cho phép.
    public static Locale requireLocale(String languageTag) {
        if (languageTag == null || languageTag.isBlank()
                || languageTag.length() > 64) {
            throw new IllegalArgumentException(
                "Locale thiếu hoặc quá dài");
        }
        Locale locale = new Locale.Builder()
            .setLanguageTag(languageTag)
            .build();

        if (!SUPPORTED_LANGUAGES.contains(locale.toLanguageTag())) {
            throw new IllegalArgumentException(
                "Locale không được hỗ trợ: " + languageTag);
        }
        return locale;
    }

    // Hợp đồng XML cực nhỏ: <order qty="N"/> và 1 <= N <= 1000.
    // Không chấp nhận DTD, namespace, phần tử con hay attr thừa.
    public static int quantityFromXml(String xml) throws Exception {
        if (xml == null || xml.isBlank() || xml.length() > 4096) {
            throw new IllegalArgumentException(
                "XML rỗng hoặc quá dài");
        }

        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException error)
                    throws SAXException {
                throw error;
            }

            @Override
            public void fatalError(SAXParseException error)
                    throws SAXException {
                throw error;
            }
        });

        Document document = builder.parse(
            new InputSource(new StringReader(xml)));
        Element order = document.getDocumentElement();

        if (order == null
                || !"order".equals(order.getTagName())
                || order.getNamespaceURI() != null
                || !order.hasAttribute("qty")
                || order.getAttributes().getLength() != 1
                || order.hasChildNodes()) {
            throw new IllegalArgumentException(
                "XML không đúng cấu trúc order");
        }

        int quantity;
        try {
            quantity = Integer.parseInt(order.getAttribute("qty"));
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                "qty không phải số nguyên", ex);
        }
        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException(
                "qty nằm ngoài [1,1000]");
        }
        return quantity;
    }

    public static void createSchema(Connection connection)
            throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.executeUpdate("""
                CREATE TABLE orders (
                    sku VARCHAR(20) NOT NULL UNIQUE,
                    qty INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 1000)
                )
                """);
        }
    }

    public static void insertOrder(Connection connection,
                                   String sku,
                                   int quantity) throws SQLException {
        if (sku == null || !sku.matches("[A-Z0-9_-]{1,20}")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException("qty không hợp lệ");
        }

        try (PreparedStatement statement =
                connection.prepareStatement(
                    "INSERT INTO orders (sku, qty) VALUES (?, ?)")) {
            statement.setString(1, sku);
            statement.setInt(2, quantity);
            statement.executeUpdate();
        }
    }

    public static Integer findQuantity(Connection connection, String sku)
            throws SQLException {
        try (PreparedStatement statement =
                connection.prepareStatement(
                    "SELECT qty FROM orders WHERE sku = ?")) {
            statement.setString(1, sku);
            try (ResultSet rows = statement.executeQuery()) {
                return rows.next() ? rows.getInt(1) : null;
            }
        }
    }

    public static int countOrders(Connection connection)
            throws SQLException {
        try (Statement statement = connection.createStatement();
             ResultSet rows = statement.executeQuery(
                 "SELECT COUNT(*) FROM orders")) {
            rows.next();
            return rows.getInt(1);
        }
    }

    // Đường đi tích hợp duy nhất: locale -> XML -> JDBC.
    public static void ingest(Connection connection,
                              String languageTag,
                              String xml,
                              String sku) throws Exception {
        requireLocale(languageTag);
        int quantity = quantityFromXml(xml);
        insertOrder(connection, sku, quantity);
    }
}
```

### Vì sao thiết kế này có thể kiểm thử độc lập?

- `requireLocale` không đọc `Locale.getDefault()`: test không phụ thuộc hệ điều hành.
- `quantityFromXml` cấu hình an toàn **trước khi parse**; mỗi lời gọi có builder riêng để tránh chia sẻ `DocumentBuilder` không an toàn giữa thread.
- `insertOrder` dùng `PreparedStatement`; database vẫn có constraint cho trường hợp validation bị bypass.
- `ingest` chỉ ghép các ranh giới; quyết định `commit/rollback` thuộc **đơn vị giao dịch của bên gọi**, giúp test batch rõ ràng.
- H2 chỉ xuất hiện ở classpath test; code chính có thể dùng `Connection` từ một driver JDBC khác.
- Với dữ liệu XML nhận từ mạng, cần thêm giới hạn byte trước khi biến thành `String`, cùng giới hạn depth/time phù hợp; ví dụ chỉ minh họa contract của một record kích thước nhỏ.

## 8. Mã kiểm thử: `src/test/java/demo/BoundaryContractsTest.java`

Dùng các assertion hiện hành của **JUnit Jupiter**, tạo **H2 database mới cho mỗi test** (URL `jdbc:h2:mem:` không có tên tạo database trong bộ nhớ riêng cho kết nối) và sử dụng try-with-resources để tự đóng `Connection`/`Statement`/`ResultSet`.

```java
package demo;

import static org.junit.jupiter.api.Assertions.*;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.IllformedLocaleException;
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.xml.sax.SAXException;

public class BoundaryContractsTest {
    private static Connection database() throws SQLException {
        Connection connection =
            DriverManager.getConnection("jdbc:h2:mem:", "sa", "");
        BoundaryContracts.createSchema(connection);
        return connection;
    }

    @Test
    void localeAcceptsCanonicalSupportedTag() {
        Locale selected = BoundaryContracts.requireLocale("vi-vn");
        assertEquals("vi-VN", selected.toLanguageTag());
    }

    @Test
    void localeRejectsIllFormedTag() {
        assertThrows(IllformedLocaleException.class,
            () -> BoundaryContracts.requireLocale("en_US"));
    }

    @Test
    void localeRejectsUnsupportedTag() {
        assertThrows(IllegalArgumentException.class,
            () -> BoundaryContracts.requireLocale("xx-ZZ"));
    }

    @Test
    void localeRejectsBlankTag() {
        assertThrows(IllegalArgumentException.class,
            () -> BoundaryContracts.requireLocale(""));
        assertThrows(IllegalArgumentException.class,
            () -> BoundaryContracts.requireLocale(null));
    }

    @Test
    void xmlAcceptsMinimalOrder() throws Exception {
        assertEquals(3, BoundaryContracts.quantityFromXml(
            "<order qty=\"3\"/>"));
    }

    @Test
    void xmlRejectsDoctypeBeforeEntityResolution() {
        String xxe = """
            <!DOCTYPE order [
              <!ENTITY leak SYSTEM "file:///etc/passwd">
            ]>
            <order qty="1">&leak;</order>
            """;
        assertThrows(SAXException.class,
            () -> BoundaryContracts.quantityFromXml(xxe));
    }

    @Test
    void xmlRejectsMalformedDocument() {
        assertThrows(SAXException.class,
            () -> BoundaryContracts.quantityFromXml(
                "<order qty=\"1\">"));
    }

    @Test
    void xmlRejectsWrongShapeAndQuantity() {
        assertThrows(IllegalArgumentException.class,
            () -> BoundaryContracts.quantityFromXml(
                "<order qty=\"0\"/>"));
        assertThrows(IllegalArgumentException.class,
            () -> BoundaryContracts.quantityFromXml(
                "<order qty=\"1001\"/>"));
        assertThrows(IllegalArgumentException.class,
            () -> BoundaryContracts.quantityFromXml(
                "<order qty=\"abc\"/>"));
        assertThrows(IllegalArgumentException.class,
            () -> BoundaryContracts.quantityFromXml(
                "<order qty=\"2\" extra=\"x\"/>"));
        assertThrows(IllegalArgumentException.class,
            () -> BoundaryContracts.quantityFromXml(
                "<order qty=\"2\"><extra/></order>"));
    }

    @Test
    void jdbcValidInsertAndRead() throws Exception {
        try (Connection connection = database()) {
            BoundaryContracts.insertOrder(connection, "SKU_1", 7);
            assertEquals(Integer.valueOf(7),
                BoundaryContracts.findQuantity(connection, "SKU_1"));
            assertEquals(1, BoundaryContracts.countOrders(connection));
        }
    }

    @Test
    void jdbcRejectsContractViolationsBeforeSql() throws Exception {
        try (Connection connection = database()) {
            assertThrows(IllegalArgumentException.class,
                () -> BoundaryContracts.insertOrder(
                    connection, "../SKU", 2));
            assertThrows(IllegalArgumentException.class,
                () -> BoundaryContracts.insertOrder(
                    connection, "GOOD", 0));
            assertThrows(IllegalArgumentException.class,
                () -> BoundaryContracts.insertOrder(
                    connection, null, 2));
            assertEquals(0, BoundaryContracts.countOrders(connection));
        }
    }

    @Test
    void jdbcConstraintRejectsDirectInvalidWrite() throws Exception {
        try (Connection connection = database();
             PreparedStatement statement =
                 connection.prepareStatement(
                     "INSERT INTO orders (sku, qty) VALUES (?, ?)")) {
            statement.setString(1, "VALID");
            statement.setInt(2, 0); // Bypass validation để thử CHECK.
            assertThrows(SQLException.class,
                () -> statement.executeUpdate());
            assertEquals(0, BoundaryContracts.countOrders(connection));
        }
    }

    @Test
    void jdbcSearchTreatsInjectionAsData() throws Exception {
        try (Connection connection = database()) {
            BoundaryContracts.insertOrder(connection, "A1", 4);
            assertNull(BoundaryContracts.findQuantity(
                connection, "A1' OR '1'='1"));
            assertEquals(Integer.valueOf(4),
                BoundaryContracts.findQuantity(connection, "A1"));
            assertEquals(1, BoundaryContracts.countOrders(connection));
        }
    }

    @Test
    void jdbcRollbackRestoresEmptyState() throws Exception {
        try (Connection connection = database()) {
            connection.setAutoCommit(false);
            BoundaryContracts.insertOrder(connection, "ROLLBACK", 5);
            assertEquals(1, BoundaryContracts.countOrders(connection));
            connection.rollback();
            assertEquals(0, BoundaryContracts.countOrders(connection));
        }
    }

    @Test
    void integrationAcceptsAllContracts() throws Exception {
        try (Connection connection = database()) {
            BoundaryContracts.ingest(
                connection, "en-US", "<order qty=\"9\"/>", "BOOK_17");
            assertEquals(Integer.valueOf(9),
                BoundaryContracts.findQuantity(connection, "BOOK_17"));
        }
    }

    @Test
    void integrationRejectsInvalidLocaleWithoutWrite() throws Exception {
        try (Connection connection = database()) {
            assertThrows(IllegalArgumentException.class,
                () -> BoundaryContracts.ingest(
                    connection, "xx-ZZ", "<order qty=\"9\"/>",
                    "BOOK_17"));
            assertEquals(0, BoundaryContracts.countOrders(connection));
        }
    }

    @Test
    void integrationRejectsXmlWithoutWrite() throws Exception {
        try (Connection connection = database()) {
            assertThrows(IllegalArgumentException.class,
                () -> BoundaryContracts.ingest(
                    connection, "vi-VN", "<order qty=\"0\"/>",
                    "BOOK_17"));
            assertEquals(0, BoundaryContracts.countOrders(connection));
        }
    }

    @Test
    void batchRollbackWhenSecondItemInvalid() throws Exception {
        try (Connection connection = database()) {
            connection.setAutoCommit(false);
            BoundaryContracts.ingest(
                connection, "vi-VN", "<order qty=\"2\"/>", "FIRST");
            assertThrows(IllegalArgumentException.class,
                () -> BoundaryContracts.ingest(
                    connection, "vi-VN", "<order qty=\"0\"/>",
                    "SECOND"));

            connection.rollback();
            assertEquals(0, BoundaryContracts.countOrders(connection));
        }
    }
}
```

**Số test:** 17 phương thức `@Test`, phân thành Locale (4), XML (4), JDBC (5), tích hợp/rollback liên miền (4). Đối với case `integrationRejectsXmlWithoutWrite`, XML bị từ chối ở kiểm tra nghiệp vụ **trước khi SQL được thực thi**. Test `jdbcConstraintRejectsDirectInvalidWrite` cố ý bỏ qua validation của service để kiểm tra database có phòng thủ độc lập.

## 9. Chạy suite và đọc kết quả

Từ thư mục có `pom.xml`:

```bash
mvn -B test
```

**Kỳ vọng khi chạy trên JDK 17+ có Maven và tải được dependency:**

```text
Tests run: 17, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **các dòng kết quả cần kiểm chứng** của Maven/Surefire, không phải toàn bộ stdout (tên class, thời gian, tiến độ tải artifact và cách trình bày có thể khác). Nếu thất bại do không lấy được dependency hoặc JVM khác Java 17+, đó là **lỗi môi trường trước test**, không phải bằng chứng logic validation sai.

Muốn chạy duy nhất một test class:

```bash
mvn -B -Dtest=BoundaryContractsTest test
```

Khi một `@Test` thất bại, Surefire trả mã lỗi nonzero; xem báo cáo trong `target/surefire-reports` và thông tin `AssertionFailedError`/`SQLException`/`SAXException` tương ứng. Trong CI phải coi mã lỗi của lệnh Maven là quyết định pass/fail. Không chỉ tìm chuỗi `BUILD SUCCESS` trong log mà bỏ qua trạng thái tiến trình.

### Các giới hạn của ví dụ có chủ đích

- H2 là **DB kiểm thử tích hợp**, không phải bản sao ngữ nghĩa của production DB. Khả năng tương thích SQL, kiểu dữ liệu, isolation và xử lý khóa cần được thử thêm trên engine thực tế.
- Không giả mạo mock database để chứng minh `CHECK`: test thực thi SQL qua JDBC driver.
- `quantityFromXml` giới hạn một chuỗi nhỏ, không thay thế giới hạn body HTTP streaming; trong sản phẩm cần cài đặt hạn mức byte/tài nguyên từ đầu nguồn.
- Demo kiểm tra mỗi bản ghi bằng ba ranh giới tuần tự. Một ứng dụng có thể thêm auth, schema validation, mapping phiên bản hợp đồng, idempotency và retry an toàn, nhưng các yêu cầu đó phải có test riêng.
- Mặc dù test dùng `jdbc:h2:mem:`, mỗi connection của bài tập là một DB riêng. Không dùng một database có tên cố định chia sẻ giữa nhiều test song song nếu không có isolation/cleanup chắc chắn.
- Nếu CI có nhà cung cấp JAXP khác hoặc cấu hình đặc biệt, test cấu hình bảo mật XML có thể thất bại ngay tại `setFeature`: **đó là tín hiệu quan trọng**, không được tắt kiểm tra chỉ để test xanh.

## 10. Chiến lược kiểm thử dữ liệu ngoài hợp đồng có hệ thống

Một bài kiểm thử tốt không chỉ chứa vài ví dụ lỗi. Nên phân hoạch dữ liệu theo **equivalence classes** và **boundary values**:

| Thuộc tính | Hợp lệ | Không hợp lệ gần biên | Không hợp lệ đối nghịch |
| --- | --- | --- | --- |
| Locale syntax | `vi-VN`, `en-US` | `""`, `en_US`, tag quá dài | Tag malformed có dấu phân cách dư; dữ liệu không phải BCP 47 |
| Locale policy | Locale trong whitelist | Tag well-formed nhưng ngoài whitelist | Tag có extension lạ làm thay đổi cách xử lý |
| XML structure | Đúng root/attr | Thiếu attr, thừa node/attr, giá trị 0/1001 | DOCTYPE, external entity, recursive expansion |
| XML parser resources | Tài liệu nhỏ | Nhiều cấp node, input vượt byte limit | Billion-laughs, file/URL entity |
| JDBC SKU | `BOOK_17` | `null`, ký tự nhỏ, hơn 20 ký tự | `' OR 1=1 --` trong tham số |
| JDBC quantity | 1, 1000 | 0, 1001, số âm | Bypass service để kích hoạt `CHECK` |
| Persistence | Một giao dịch commit đủ | Không có dữ liệu khi validation fail | Một bản ghi fail sau bản ghi đầu, phải rollback |
| Concurrency | Test độc lập DB/schema | Chạy lặp nhiều lần | Hai worker sửa cùng một row, racing unique constraint |

### Test đủ lớp nhưng không trùng trách nhiệm

- **Validation** trả `IllegalArgumentException`/`IllformedLocaleException` cho dữ liệu sai; kiểm tra lỗi được truyền tới API boundary dưới mã lỗi ứng dụng phù hợp (thường lỗi 4xx), không rò stack trace nội bộ.
- **Parser** ném `SAXException`/`SAXParseException` cho XML sai cú pháp hoặc bị cấm; ứng dụng cần map thành lỗi client khi đó là input không hợp đồng, trong khi parser config unsupported thường là lỗi cấu hình server.
- **JDBC** ném `SQLException` khi DB từ chối dữ liệu/không khả dụng; không giả định mọi vendor trả cùng SQLState hay câu chữ thông báo.
- **Giao dịch** phải dùng `rollback` khi có lỗi sau một hoặc nhiều lần ghi. Với hệ phân tán/queue/event, cơ chế rollback JDBC không thể tự rollback hành động đã gửi tới một hệ thống khác; cần thiết kế outbox/idempotency hoặc cơ chế nhất quán khác.

Nên dùng assertion dựa trên **hành vi bất biến**: số hàng, giá trị đọc lại, loại lỗi và kết quả không có side effect. Hạn chế dựa vào **thông báo exception nguyên văn** do JDK, driver hoặc parser cung cấp vì thay đổi theo phiên bản và locale.

### Fuzz/property-based test và dữ liệu ngẫu nhiên

Có thể tăng độ bao phủ bằng generator tạo locale tags, XML structures, SKU và quantity ở biên. Tuy nhiên, test property-based phải giữ **seed có thể tái lập**, có shrink/case report khi fail và giới hạn tài nguyên. Với XML, fuzzing nên chạy trong môi trường cách ly có hạn mức để tránh hại chính hạ tầng CI.

Bộ dữ liệu kiểm thử nên lưu dưới tên thể hiện kỳ vọng, ví dụ `valid/vi-vn-order.xml`, `invalid/xxe-doctype.xml`, `invalid/quantity-zero.xml`. Không lưu XML có đường dẫn bí mật thật của hệ thống hay credentials trong repository. Nếu test cần database production-like, dùng dữ liệu sinh tổng hợp thay vì dump dữ liệu khách hàng.

## 11. Những lỗi thiết kế cần tránh

| Sai lầm | Tại sao không đủ? | Cách làm hiện hành |
| --- | --- | --- |
| `Locale.forLanguageTag` rồi tin mọi đầu vào | Parser lenient và locale cú pháp đúng vẫn có thể không được hỗ trợ | `Locale.Builder` nghiêm ngặt + whitelist |
| Dùng `Locale.setDefault` ở nhiều test | Ảnh hưởng toàn JVM, gây test chập chờn | Truyền `Locale` tường minh |
| Chỉ bật `FEATURE_SECURE_PROCESSING` để chống XXE | Không phải mọi đường external access mặc định đều bị chặn | Cấm DTD khi không cần + EAP bằng chuỗi rỗng + fail closed |
| Tin `setExpandEntityReferences(false)` là biện pháp duy nhất | Chỉ ảnh hưởng cách biểu diễn entity trong DOM | Chặn DOCTYPE và resource bên ngoài |
| XML well-formed nên cho vào DB | Chưa kiểm tra hợp đồng/schema, miền giá trị | Validate cấu trúc + giá trị sau khi parse |
| Bắt mọi exception và trở về `qty=0` | Biến input sai thành dữ liệu có vẻ hợp lệ | Trả lỗi rõ, không ghi trạng thái |
| Nối `sku` vào câu SQL | SQL injection | `PreparedStatement` và bind tham số |
| Chỉ test validation ở service | Code khác có thể ghi thẳng DB | Constraint ở database + test bypass |
| Giả định H2 tương đương mọi RDBMS | SQL dialect/driver/transaction khác nhau | Chạy thêm suite trên production DB |
| Thử sai đầu vào mà chỉ kiểm tra exception | Có thể đã ghi một phần trước khi lỗi | Kiểm tra trạng thái DB sau lỗi + rollback |
| Test share database không dọn | Flaky do test order và dữ liệu cũ | DB riêng mỗi test, transaction/cleanup rõ |
| Hardcode message `SAXParseException` | Message phụ thuộc parser/version | Assert loại lỗi, không có external fetch/side effect |
| Dùng JUnit 4 runner cũ để bắt đầu project mới | Không tận dụng JUnit Jupiter hiện hành | JUnit 6 / Jupiter với Maven Surefire hiện đại |
| Chạy build trên môi trường có quyền rộng | XML/fuzzer/SQL fixture có thể nguy hiểm nếu cấu hình sai | Chạy CI ít quyền, network egress được kiểm soát |

**Không đánh tráo thất bại:** test loại `XXE` không “pass” nếu parser đã đọc file trước rồi ném lỗi nghiệp vụ. Thiết kế ở đây cấm DOCTYPE từ đầu; với sản phẩm có XML schema/DTD hợp lệ, cần resolver/cátalog cho tài nguyên được phép và test bằng môi trường có giám sát kết nối ngoài để chắc chắn không có external access trái phép.

## 12. Checklist trước khi đưa vào hệ thống thật

1. Viết **hợp đồng đầu vào có phiên bản**: locale nào, schema/XML namespace nào, domain số lượng/SKU nào và tình huống không hỗ trợ phải trả gì.
2. Tách parser, validation, mapping và persistence để kiểm thử từng ranh giới; đường tích hợp dùng cùng các hàm đã kiểm tra.
3. Kiểm tra locale syntax **và** allowed values, không phụ thuộc default locale của CI.
4. XML parser phải có chính sách entity/DTD, external access, giới hạn input và chống DoS, không bị cấu hình “fail open”.
5. Truy vấn JDBC phải parameterized; có constraints ở DB, không dựa vào service validation làm lớp duy nhất.
6. Giao dịch phải commit toàn bộ hoặc rollback; kiểm tra cả số hàng sau lỗi.
7. Chạy cả positive/negative/boundary/security tests và case tổng hợp qua locale → XML → JDBC.
8. Pin dependency, chạy test bằng JDK và JUnit được hỗ trợ; kiểm tra compatibility/upgrade trên matrix CI.
9. Có lớp test với **DB engine/driver production** và môi trường mạng/trust/permissions thực tế, ngoài H2 smoke suite.
10. Lưu test report, seed, case tái hiện; tránh test dựa vào thứ tự, thời điểm, thông báo lỗi thay đổi theo nhà cung cấp.

## 13. Tài liệu tham khảo còn hiệu lực

- [Java SE 17 — Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): kiểm tra cú pháp BCP 47, khác `Locale.forLanguageTag` lenient.
- [Java SE 25 — Locale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): tag, locale normalization và API hiện hành.
- [Oracle — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): cấm DTD, `FEATURE_SECURE_PROCESSING`, hạn chế truy cập tài nguyên bên ngoài.
- [Java SE 17 — DocumentBuilderFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): các thuộc tính, feature và lỗi cấu hình.
- [OWASP — XML External Entity Prevention](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): nguyên tắc hardening DOM/SAX/StAX.
- [Java SE 25 — PreparedStatement](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html): bind parameter và kết quả JDBC.
- [Java SE 25 — Connection](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Connection.html): transaction, `setAutoCommit`, `commit`, `rollback`.
- [JUnit 6.1.3 User Guide](https://docs.junit.org/6.1.3/): Jupiter, assertions, vòng đời test và tích hợp Maven; JUnit 6 yêu cầu Java 17+.
- [H2 Database Engine](https://h2database.github.io/): embedded/in-memory JDBC, phụ thuộc `com.h2database:h2:2.5.252`.
- [Apache Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit.html): chạy Jupiter tests bằng Maven Surefire 3.6+.

**Kết luận:** Kết hợp **Locale.Builder + kiểm tra whitelist**, **JAXP parser được harden + kiểm tra cấu trúc và giá trị**, **JDBC PreparedStatement + DB constraints + transaction rollback**, rồi kiểm tra chúng **cùng một đường dữ liệu**. Đây là cách bảo vệ hợp đồng đầu vào có thể tái lập, chứ không phải chỉ kiểm tra các hàm riêng lẻ trên dữ liệu “đẹp”.