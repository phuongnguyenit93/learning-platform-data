# Kiểm thử DN có ký tự đặc biệt và Unicode

Một API danh bạ nhận tên nhân viên `Nguyễn, An`. Nếu lập trình viên tạo DN bằng cách nối `"cn=" + name + ",ou=people"`, dấu phẩy trong tên có thể bị hiểu thành dấu phân tách hai thành phần DN. Với `An+Minh`, dấu cộng không escape có thể trở thành dấu phân tách các attribute trong **RDN đa trị**. Với `" Trần "`, khoảng trắng ở đầu/cuối cũng có ý nghĩa cú pháp. Và nếu tên chứa `Đặng Thị Mỹ` hoặc ký tự tổ hợp Unicode, việc chuyển đổi chuỗi một cách tùy tiện có thể dẫn đến tìm không thấy entry, đổi sai tên hoặc đồng bộ trùng người.

Trong module **SPRING_DATA_LDAP**, entry được xác định bằng **Distinguished Name (DN)**, truy cập qua `ContextSource`, `LdapTemplate` hoặc Spring Data LDAP repository và ánh xạ theo `@Entry`/`@Id`/`@DnAttribute`. Bài thuộc chương **Kiểm thử** này hướng dẫn xây bộ kiểm thử chuyên biệt cho **DN chứa ký tự đặc biệt và Unicode**: từ JNDI `LdapName`/`Rdn`, `LdapNameBuilder` của Spring LDAP, đến tạo/đọc/đổi tên entry trên directory thử nghiệm, kiểm tra filter an toàn, schema, ACL và Unicode normalization.

**Nguyên tắc:** không tự nối một giá trị RDN chưa tin cậy vào chuỗi DN. Hãy dùng API DN có cấu trúc, kiểm thử round-trip và xác minh bằng LDAP server thực tế. Đây là bài kiểm thử **định danh LDAP**, không phải bài kiểm tra SQL hay URL encoding.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt **DN string theo RFC 4514**, **LDAP search filter theo RFC 4515** và **LDIF theo RFC 2849**.
2. Viết bảng test cho dấu phẩy, cộng, bằng, gạch chéo ngược, dấu nháy, dấu chấm phẩy, dấu `#` đầu chuỗi, khoảng trắng đầu/cuối và các ký tự Unicode.
3. Sử dụng `LdapNameBuilder.add("cn", value)`, `LdapName` và `Rdn` để tạo/đọc DN thay vì ghép chuỗi thủ công.
4. Kiểm tra **round-trip giá trị RDN** và hiểu tại sao không nên so sánh chuỗi DN hiển thị theo từng ký tự.
5. Phân biệt Unicode NFC/NFD, quy tắc matching của directory và chính sách chuẩn hóa của ứng dụng.
6. Viết unit test JUnit 5 và integration test `LdapTemplate` đối với entry trong **OU riêng của môi trường test**.
7. Kiểm chứng lookup, search, rename, giới hạn base/ACL và xử lý lỗi mà không gây LDAP injection hoặc sửa dữ liệu thật.

## 2. Nền tảng: DN, RDN và attribute

Giả sử directory có cây:

~~~text
dc=example,dc=org
├── ou=people
│   └── cn=Lan Nguyen
├── ou=dn-test
│   ├── cn=Mai\, Nguyễn
│   ├── cn=An\+Minh
│   └── cn=Đặng Thị Mỹ
└── ou=services
    └── cn=lab-reader
~~~

Trong biểu diễn DN:

~~~text
cn=Mai\, Nguyễn,ou=dn-test,dc=example,dc=org
└──── RDN ──────┘ └──────────── phần còn lại ──────────┘
~~~

- **DN** là tên đầy đủ của một entry trong cây, gồm các Relative Distinguished Name.
- **RDN** là thành phần định danh tương đối với entry cha, ví dụ `cn=Mai\, Nguyễn`.
- **Tên attribute trong RDN** là `cn`; **giá trị** thực tế là `Mai, Nguyễn` (dấu phẩy là dữ liệu, không phải phần phân tách).
- **Context base** có thể là `dc=example,dc=org`; khi đó mã Spring LDAP thường làm việc với DN tương đối như `cn=Mai\, Nguyễn,ou=dn-test`.
- **Schema/`objectClass`** quyết định entry có được dùng `cn`, `sn` và những thuộc tính liên quan hay không.

**Không nhầm dấu phân cách với dữ liệu thực:** `cn=An\+Minh` là một RDN có giá trị `An+Minh`, còn `cn=An+uid=Minh` có thể là **RDN đa trị**, chứa hai cặp attribute–value. Đây là hai DN khác nhau về cấu trúc và không thể hoán đổi.

### 2.1. Ba chuẩn mã hóa khác nhau

| Ngữ cảnh | Chuẩn / API thích hợp | Ví dụ / mục đích |
| --- | --- | --- |
| **DN string** | RFC 4514, JNDI `LdapName`/`Rdn`, Spring LDAP `LdapNameBuilder`. | Biểu diễn DN, escape dấu phẩy, cộng, khoảng trắng đặc biệt. |
| **Search filter** | RFC 4515, `LdapQueryBuilder.where(...).is(value)`, `EqualsFilter`. | Escape `*`, `(`, `)`, `\` và byte NUL trong giá trị filter. |
| **LDIF** | RFC 2849, biểu diễn dòng, Base64 khi cần. | Xuất/nhập entry; có thể dùng `dn::` nếu DN cần mã hóa Base64. |
| **URL/HTTP** | URL percent encoding, framework đọc query/path parameter. | Chuyển dữ liệu qua HTTP; **không thay thế** DN/filter escaping. |

Một giá trị như `An, Minh` phải được **DN-escape** khi trở thành RDN, và phải được **filter-escape** nếu được đưa vào `(cn=...)`. Đừng escape theo RFC 4514 rồi dùng chuỗi đã escape như một giá trị filter; hai ngữ cảnh khác nhau.

## 3. Danh mục ký tự cần kiểm thử

RFC 4514 quy định cú pháp DN string và các trường hợp cần escape, bao gồm những ký tự dành riêng. Tùy JDK/LDAP provider, dạng chuỗi `toString()` có thể chọn cách escape tương đương nhau (ví dụ dạng hex hay gạch chéo ngược). Quan trọng nhất là **cấu trúc DN và giá trị RDN được bảo toàn**.

| Giá trị gốc của `cn` | Ký tự cần chú ý | Điều cần chứng minh |
| --- | --- | --- |
| `Mai, Nguyễn` | Dấu phẩy `,`. | Không tạo thêm một RDN. |
| `An+Minh` | Dấu cộng `+`. | Vẫn là **một giá trị cn**, không bị tách thành RDN đa trị. |
| `QA=Automation` | Dấu bằng `=`. | Dấu bằng nằm trong giá trị, không mở cặp attribute mới. |
| `An\Bình` | Gạch chéo ngược `\`. | Ký tự `\` gốc không bị mất hay diễn giải thành escape mới. |
| `"Mai"` | Nháy kép `"`. | Parse lại DN khôi phục dấu nháy. |
| `An;Minh` | Dấu chấm phẩy `;`. | DN không bị tách sai ở những parser hỗ trợ cú pháp tương thích. |
| `#Thủy` | `#` ở đầu giá trị. | Không bị hiểu là biểu diễn hex của giá trị RDN. |
| ` Lan` | Khoảng trắng đầu chuỗi. | Không bị loại bỏ ngoài ý muốn. |
| `Lan ` | Khoảng trắng cuối chuỗi. | Không bị mất trong round-trip. |
| `<An>` | Dấu `<` và `>`. | Giá trị được bảo toàn khi tạo DN. |
| `Đặng Thị Mỹ` | Unicode dựng sẵn. | Không mất dấu khi qua Java/JNDI. |
| `Trần Văn Ánh` | Unicode có nhiều dấu thanh. | Chuyển mã UTF-8 và lookup đúng với môi trường thực. |
| `李小龍` | Ký tự ngoài Latin. | Không giả định dữ liệu chỉ ASCII. |
| `Nguyễn 👩‍💻` | Unicode ngoài BMP và chuỗi ký tự kết hợp. | Java không làm mất surrogate pair/ký tự khi round-trip. |

**Phạm vi test:** Unit test JNDI có thể xác minh nhiều giá trị hơn khả năng schema của từng LDAP server. Một directory nhất định có thể không cho phép emoji, ký tự điều khiển, tên quá dài hoặc attribute sai schema; **test DN syntax PASS không đồng nghĩa LDAP Add sẽ được server chấp nhận**.

### 3.1. Một DN string hợp lệ có thể có nhiều biểu diễn

Ví dụ, một số ký tự có thể được escape bằng ký tự `\` hoặc bằng các octet hex theo RFC 4514. Khi Java `Name.toString()` dựng biểu diễn lại, không nên cố định mọi dấu slash ở đúng vị trí mà không có yêu cầu định dạng cụ thể.

Đối với unit test, ưu tiên:

1. Số lượng RDN đúng.
2. Loại RDN cuối đúng, ví dụ `cn`.
3. `Rdn.getValue()` trả lại **giá trị gốc**.
4. Phần base được giữ như đã khai báo.
5. Parse lại từ `Name.toString()` vẫn thu được cùng cấu trúc.

Việc so sánh chuỗi DN nguyên văn bằng `equals(String)` có thể sai vì chữ hoa/thường của tên attribute, các dạng escape hợp lệ hoặc cách server chuẩn hóa kết quả. Nếu dùng DN như khóa trong hệ thống ứng dụng, cần chính sách định danh, không chỉ lưu chuỗi DN hiển thị.

## 4. Cách dựng DN an toàn với Spring LDAP

### 4.1. Phản ví dụ: nối chuỗi

~~~java
// KHÔNG AN TOÀN:
String userCn = inputFromClient;
String relativeDn = "cn=" + userCn + ",ou=dn-test";
~~~

Với `inputFromClient = "Mai, Nguyễn"`, chuỗi `cn=Mai, Nguyễn,ou=dn-test` **không biểu diễn** giá trị cn có dấu phẩy theo cách mong muốn. Với giá trị có dấu cộng, client có thể thay đổi cấu trúc RDN.

### 4.2. Dùng `LdapNameBuilder.add(type, value)`

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DnFactory {

    private DnFactory() {}

    public static Name personDn(String commonName) {
        return LdapNameBuilder.newInstance("ou=dn-test")
                .add("cn", commonName)
                .build();
    }
}
~~~

Gọi:

~~~java
Name relativeDn = DnFactory.personDn("Mai, Nguyễn");
System.out.println(relativeDn);
// Một biểu diễn tương đương: cn=Mai\, Nguyễn,ou=dn-test
~~~

`add("cn", commonName)` nhận **giá trị RDN**, không nhận một chuỗi DN đã ghép. API DN có cấu trúc xử lý escape đúng ngữ cảnh, để dấu phẩy trong dữ liệu không trở thành dấu phân cách.

Đừng đưa nguyên chuỗi `"cn=Mai, Nguyễn"` vào đối số **giá trị** rồi kỳ vọng API tự hiểu đó là một cặp type/value; nếu dùng như vậy, toàn bộ chuỗi có thể trở thành **giá trị literal** của một RDN `cn`.

### 4.3. Tạo DN bằng JNDI thuần

Nếu không dùng Spring LDAP, Java cũng có:

~~~java
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;

Rdn leaf = new Rdn("cn", "Mai, Nguyễn");
LdapName full = new LdapName(
        "ou=dn-test,dc=example,dc=org");

// Thêm RDN ở đầu tên DN theo cấu trúc JNDI.
full.add(leaf);

System.out.println(full);
~~~

Đây là ví dụ dùng API RDN theo cấu trúc; thứ tự trong `LdapName.getRdns()` được JNDI biểu diễn từ **RDN ít đặc hiệu nhất tới đặc hiệu nhất**, khác thứ tự thường thấy khi đọc DN string từ trái sang phải. Do đó, test cần xác định đúng vị trí của RDN lá.

## 5. Unit test JUnit 5: round-trip những giá trị đặc biệt

Mục tiêu: tạo DN từ giá trị raw, chuyển thành chuỗi rồi parse lại, kiểm tra **số RDN và đúng giá trị**. Không phụ thuộc LDAP server, schema hoặc kết nối.

### 5.1. Dependency

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Trong dự án Spring Boot, starter test thường đã cung cấp JUnit Jupiter. Kiểm tra version dependency do BOM quản lý khi triển khai thực tế.

### 5.2. Test parameterized

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.stream.Stream;
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.ldap.support.LdapNameBuilder;

class DistinguishedNameRoundTripTest {

    static Stream<String> validCnValues() {
        return Stream.of(
                "Mai, Nguyễn",       // dấu phẩy
                "An+Minh",           // dấu cộng
                "QA=Automation",     // dấu bằng
                "An\\Bình",          // dấu backslash
                "\"Mai\"",          // nháy kép
                "An;Minh",           // dấu chấm phẩy
                "#Thủy",             // dấu # ở đầu
                " Lan",              // khoảng trắng đầu
                "Lan ",              // khoảng trắng cuối
                "<An>",              // dấu < và >
                "Đặng Thị Mỹ",
                "Trần Văn Ánh",
                "李小龍",
                "Nguyễn 👩‍💻"
        );
    }

    @ParameterizedTest
    @MethodSource("validCnValues")
    void safelyBuildsAndParsesRdn(String rawCn) throws Exception {
        Name built = LdapNameBuilder.newInstance(
                "ou=dn-test,dc=example,dc=org")
                .add("cn", rawCn)
                .build();

        LdapName parsed = new LdapName(built.toString());
        assertEquals(4, parsed.size());

        // RDN cuối trong getRdns() là leaf 'cn' (đặc hiệu nhất).
        Rdn leaf = parsed.getRdn(parsed.size() - 1);
        assertTrue("cn".equalsIgnoreCase(leaf.getType()));
        assertEquals(rawCn, leaf.getValue());

        // Parser hai chiều bảo toàn cấu trúc DN.
        assertEquals(built, parsed);
    }
}
~~~

**Điểm cần quan sát:** Khi input là `"Mai, Nguyễn"`, test không đếm một dấu phẩy trong chuỗi hiển thị mà kiểm tra `parsed.size() == 4` và `leaf.getValue()`. Nếu bạn dùng phép nối chuỗi sai, parser có thể báo lỗi DN hoặc thêm RDN ngoài ý muốn. Với `"An+Minh"`, test chứng minh đây vẫn là **một** RDN `cn` thay vì một RDN đa trị.

### 5.3. Test chống thay đổi cấu trúc do input giống DN

Một giá trị không tin cậy có thể trông như đoạn DN:

~~~text
cn=Admin,ou=services
~~~

Nếu bạn coi đó là **giá trị literal của cn**, nó không được phép thoát ra nhánh `ou=dn-test`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import javax.naming.ldap.LdapName;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.support.LdapNameBuilder;

class DnStructureSafetyTest {

    @Test
    void dnLikeValueCannotChangeBaseOrRdnCount() throws Exception {
        String untrusted = "cn=Admin,ou=services";

        LdapName name = new LdapName(
                LdapNameBuilder.newInstance(
                        "ou=dn-test,dc=example,dc=org")
                        .add("cn", untrusted)
                        .build().toString());

        assertEquals(4, name.size());
        assertEquals(untrusted,
                name.getRdn(name.size() - 1).getValue());
        assertEquals("ou=dn-test",
                name.getRdn(name.size() - 2).toString());
    }
}
~~~

Ở đây test xác nhận việc dùng `LdapNameBuilder.add(type, value)` giữ nguyên **phần base do server chọn**. Điều đó không có nghĩa một caller được phép tự chọn bất kỳ DN hoặc OU nào; authorization và ACL vẫn phải được thực thi riêng.

## 6. Unicode: NFC, NFD và sự khác nhau khó nhìn thấy

Hai chuỗi có thể **trông giống nhau với người đọc** nhưng chứa những code point khác nhau. Ví dụ một chữ có dấu có thể là ký tự Unicode dựng sẵn (precomposed) hoặc chữ nền theo sau dấu tổ hợp (combining mark).

~~~text
NFC:  ký tự đã tổ hợp nếu có dạng dựng sẵn
NFD:  ký tự nền + các dấu kết hợp được phân tách

Hai chuỗi nhìn gần như giống nhau
nhưng UTF-8 bytes và String.equals() có thể khác.
~~~

**Đây là vấn đề khác với DN escaping.** Escape xử lý ký tự có vai trò cú pháp; normalization xử lý cách biểu diễn Unicode của cùng nội dung theo quy tắc chuẩn hóa.

### 6.1. Test NFC/NFD trên JVM

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import org.junit.jupiter.api.Test;

class UnicodeNormalizationTest {

    @Test
    void nfcAndNfdMayLookSameButHaveDifferentBytes() {
        String nfc = Normalizer.normalize(
                "Nguyễn", Normalizer.Form.NFC);
        String nfd = Normalizer.normalize(
                "Nguyễn", Normalizer.Form.NFD);

        assertNotEquals(nfc, nfd);
        assertFalse(java.util.Arrays.equals(
                nfc.getBytes(StandardCharsets.UTF_8),
                nfd.getBytes(StandardCharsets.UTF_8)));

        assertEquals(nfc, Normalizer.normalize(
                nfd, Normalizer.Form.NFC));
    }
}
~~~

Với Unicode normalization, **không mặc định LDAP server so khớp NFC và NFD theo cùng cách**. Một số matching rule có chuẩn hóa, một số directory/schema có hành vi đặc thù. Java `LdapName`, LDAP server và hệ thống đồng bộ ngoài LDAP **không nhất thiết có chung chính sách Unicode**.

### 6.2. Chính sách normalization cho ứng dụng

Nếu ứng dụng cấp tên cho **entry mới**, bạn có thể cân nhắc chuẩn hóa **NFC trước khi tạo DN và trước khi ghi attribute**. Tuy nhiên:

- Đây phải là **quy tắc thống nhất và được công bố** ở tầng ứng dụng, không phải thay đổi âm thầm trong mapper.
- Khi **đọc hoặc lookup entry đã tồn tại**, không tự biến đổi tên/RDN rồi đoán DN mới; điều đó có thể làm sai định danh đối tượng hiện có.
- Không áp đặt `String.toLowerCase()` hoặc bỏ dấu tiếng Việt để tạo DN. Những thao tác đó làm thay đổi tên và có thể gây trùng/collision.
- Nếu hệ thống chuyển sang server khác, phải kiểm tra matching rule và migration của identifier trước khi áp chính sách mới.

Thí dụ hàm chuẩn hóa **chỉ dành cho quy trình tạo mới đã chốt chính sách**:

~~~java
import java.text.Normalizer;

public final class DisplayNamePolicy {

    private DisplayNamePolicy() {}

    public static String toNfcForNewEntry(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Ten khong duoc null");
        }
        return Normalizer.normalize(raw, Normalizer.Form.NFC);
    }
}
~~~

**Không dùng** `Normalizer.normalize(...)` để “sửa” DN từ directory trước mỗi thao tác delete/rename khi chưa có bằng chứng matching rule và yêu cầu dữ liệu tương thích.

## 7. Ký tự đặc biệt nào nên được giữ, ký tự nào cần từ chối?

Escape đúng cú pháp **không thay thế validation**. Một tên có dấu phẩy, cộng, khoảng trắng đầu/cuối hoặc Unicode có thể là dữ liệu hợp lệ; nhưng ứng dụng có thể đặt giới hạn theo nghiệp vụ và schema.

| Tình huống | Hành vi khuyến nghị |
| --- | --- |
| Tên chứa dấu phẩy, cộng, bằng, dấu gạch chéo ngược. | Cho phép nếu nghiệp vụ hợp lệ, dựng DN bằng API cấu trúc. |
| Tên chứa chữ tiếng Việt, Hán tự hoặc ký tự ngoài BMP. | Kiểm tra khả năng server/schema; không mặc định cấm Unicode. |
| Tên rỗng hoặc chỉ toàn khoảng trắng. | Thường từ chối ở validation cấp ứng dụng. |
| Tên chứa NUL, CR, LF hoặc ký tự điều khiển. | Thường từ chối theo policy để tránh dữ liệu khó quản lý/log injection. |
| Tên vượt giới hạn độ dài nghiệp vụ. | Từ chối rõ ràng; không tự cắt chuỗi làm thay đổi DN. |
| Tên có khoảng trắng đầu/cuối. | Quyết định chính sách rõ: **giữ và escape**, hoặc từ chối. Không tự `trim` rồi âm thầm đổi tên. |
| Tên có Unicode surrogate không hợp lệ. | Từ chối chuỗi không hợp lệ trước khi encode UTF-8. |

### 7.1. Hàm validation minh họa

~~~java
public final class RdnValuePolicy {

    private RdnValuePolicy() {}

    public static String requireValidCommonName(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("cn khong hop le");
        }

        // Đếm Unicode code point thay vì UTF-16 code unit.
        int count = value.codePointCount(0, value.length());
        if (count > 128) {
            throw new IllegalArgumentException("cn qua dai");
        }

        // Duyệt code point để phát hiện ký tự điều khiển và
        // surrogate lẻ chưa tạo thành một Unicode scalar hợp lệ.
        for (int i = 0; i < value.length();) {
            int codePoint = value.codePointAt(i);
            if (Character.isISOControl(codePoint)
                    || (codePoint >= 0xD800 && codePoint <= 0xDFFF)) {
                throw new IllegalArgumentException(
                        "cn chua ky tu dieu khien/Unicode khong hop le");
            }
            i += Character.charCount(codePoint);
        }

        return value; // Giữ nguyên dữ liệu; không trim/lowercase.
    }
}
~~~

Giới hạn `128 code point` là **ví dụ nghiệp vụ**, không phải giới hạn DN chung của LDAP. LDAP server/schema có thể có quy tắc khác về giá trị attribute, độ dài và ký tự. Ứng dụng nên kiểm thử những trường hợp lỗi thực tế, và dùng một quy tắc nhất quán cho tất cả đường **create/rename**.

### 7.2. Test validation

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RdnValuePolicyTest {

    @Test
    void retainsSyntaxCharactersWhenBusinessRulesAllow() {
        assertEquals(" Mai, Nguyễn ",
                RdnValuePolicy.requireValidCommonName(
                        " Mai, Nguyễn "));
    }

    @Test
    void rejectsControlsAndInvalidInput() {
        assertThrows(IllegalArgumentException.class,
                () -> RdnValuePolicy.requireValidCommonName(null));
        assertThrows(IllegalArgumentException.class,
                () -> RdnValuePolicy.requireValidCommonName("  "));
        assertThrows(IllegalArgumentException.class,
                () -> RdnValuePolicy.requireValidCommonName(
                        "Mai" + (char) 0 + "Nguyen"));
        assertThrows(IllegalArgumentException.class,
                () -> RdnValuePolicy.requireValidCommonName(
                        "Mai\nNguyen"));
        assertThrows(IllegalArgumentException.class,
                () -> RdnValuePolicy.requireValidCommonName(
                        String.valueOf((char) 0xD800)));
    }
}
~~~

Điểm cần nhớ: **tên chứa ký tự có ý nghĩa trong DN không tự động là tên độc hại**. Nếu ứng dụng cần hỗ trợ người dùng có dấu phẩy trong tên, cách đúng là escape bằng `LdapNameBuilder`, không phải xóa dấu phẩy khỏi tên.

## 8. Kiểm thử DN khác kiểm thử LDAP filter

LDAP **DN** và LDAP **search filter** không dùng chung bộ ký tự escape. Đây là nguồn lỗi phổ biến nhất khi xử lý username và tên hiển thị chứa dấu ngoặc, dấu sao, gạch chéo ngược.

Giả sử người dùng gửi:

~~~text
Mai*(Nguyễn)
~~~

Hai thao tác khác nhau:

~~~java
// Dùng giá trị làm cn trong DN:
Name dn = LdapNameBuilder.newInstance("ou=dn-test")
        .add("cn", userInput)
        .build();

// Dùng giá trị làm assertion value trong search filter:
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=dn-test")
        .where("cn").is(userInput);
~~~

Ở trường hợp DN, `Rdn`/`LdapNameBuilder` xử lý giá trị theo RFC 4514. Ở trường hợp filter, `.is(userInput)` của Spring LDAP escape giá trị theo RFC 4515 (ví dụ `*` và dấu ngoặc), không cho input tạo wildcard hoặc nhánh filter không được chỉ định.

### 8.1. Unit test escape giá trị filter

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class LdapFilterEscapingTest {

    @Test
    void escapingValueDoesNotIntroduceFilterOperators() {
        String raw = "Mai*(Nguyễn)";
        String encoded = new EqualsFilter("cn", raw)
                .encode()
                .toLowerCase(Locale.ROOT);

        assertTrue(encoded.startsWith("(cn="));
        assertTrue(encoded.contains("\\2a")); // * literal
        assertTrue(encoded.contains("\\28")); // (
        assertTrue(encoded.contains("\\29")); // )
    }
}
~~~

Không lấy `dn.toString()` từ trường hợp DN rồi đặt vào giá trị filter và cho rằng đã an toàn/đúng ý nghĩa. Nếu muốn tìm theo **DN**, hãy dùng API lookup theo `Name` khi đã xác định đúng entry, hoặc biểu thức filter phù hợp schema và giá trị cần tìm.

### 8.2. Phân biệt lỗi logic và lỗi permission

Nếu lookup theo DN có Unicode trả “không thấy entry”, nguyên nhân có thể là:

- Dữ liệu RDN thực khác chuỗi đầu vào (dấu/cách normalization).
- DN tương đối sai base hoặc OU đã thay đổi.
- Server áp ACL hoặc referral làm entry không khả dụng.
- Entry bị rename nhưng client dùng DN cũ.
- Schema/matching rule của attribute không giống giả định.

**Không giải quyết lỗi này bằng cách bỏ escape và tự ghép DN thô.**

## 9. Kiểm thử tích hợp: tạo, đọc, tìm và dọn entry

Unit test xác nhận cú pháp Java. Integration test mới kiểm tra được **schema của server, quy tắc matching, TLS, ACL và hành vi LDAP thật**.

### 9.1. Chuẩn bị directory riêng

Chỉ sử dụng một OU của **môi trường thử nghiệm**, ví dụ:

~~~text
dc=example,dc=org
└── ou=dn-test
    └── (các entry được tạo và xóa trong test)
~~~

Entry cha `ou=dn-test,dc=example,dc=org` phải được tạo từ trước. Tài khoản chạy integration test chỉ được cấp quyền add/read/search/delete trên OU test (và rename nếu có bài test rename), không dùng tài khoản quản trị production.

`application-ldap-test.yml` được **người học cấu hình trong dự án của mình**:

~~~yaml
spring:
  ldap:
    urls: ${LDAP_TEST_URL:ldaps://ldap-test.example.org:636}
    base: ${LDAP_TEST_BASE_DN:dc=example,dc=org}
    username: ${LDAP_TEST_BIND_DN}
    password: ${LDAP_TEST_BIND_PASSWORD}
~~~

Không hardcode mật khẩu trong Git. LDAPS/StartTLS phải được cấu hình chứng chỉ tin cậy trong JVM; không tắt certificate validation cho test rồi vô tình mang cấu hình đó sang production.

### 9.2. Integration test `LdapTemplate.bind` và `lookup`

Ví dụ JUnit 5 + Spring Boot, chỉ chạy khi người học chủ động bật biến môi trường `LDAP_INTEGRATION_TEST=true` và đã cung cấp endpoint test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("ldap-test")
@EnabledIfEnvironmentVariable(
        named = "LDAP_INTEGRATION_TEST", matches = "true")
class UnicodeDnIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void createsAndLooksUpEntryWithCommaAndVietnamese() {
        String cn = "Nguyễn, An-" + UUID.randomUUID();

        Name dn = LdapNameBuilder.newInstance("ou=dn-test")
                .add("cn", cn)
                .build();

        Attributes attrs = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);
        attrs.put("cn", cn);
        attrs.put("sn", "Test");

        boolean created = false;
        try {
            // Chỉ ADD trong OU test đã tồn tại.
            ldapTemplate.bind(dn, null, attrs);
            created = true;

            String actualCn = ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) result ->
                            result.get("cn").get().toString());

            assertEquals(cn, actualCn);
        } finally {
            if (created) {
                // Xóa đúng DN do test vừa tạo.
                ldapTemplate.unbind(dn);
            }
        }
    }
}
~~~

**Giới hạn của ví dụ:** Nó cần project Spring Boot, Spring LDAP, kết nối và OU test đã cấu hình; không tự tạo directory. Phải kiểm tra `objectClass` và attribute bắt buộc theo schema server. Nếu bind được thực hiện thành công nhưng response bị mất trước khi biến `created` chuyển thành true, entry test có thể còn trên server; trong CI nên có cơ chế đối soát/dọn dữ liệu test theo nhãn, không xóa cả OU bừa bãi.

### 9.3. Test tìm bằng filter và so sánh với lookup

Sau khi tạo entry, hãy kiểm tra hai đường đọc:

~~~java
// LOOKUP: đã biết DN tương đối đúng.
String byDn = ldapTemplate.lookup(
        dn,
        (AttributesMapper<String>) attributes ->
                attributes.get("cn").get().toString());

// SEARCH: tìm theo attribute cn, dùng builder escape giá trị.
LdapQuery q = LdapQueryBuilder.query()
        .base("ou=dn-test")
        .where("cn").is(cn);

List<String> matches = ldapTemplate.search(
        q,
        (AttributesMapper<String>) attributes ->
                attributes.get("cn").get().toString());
~~~

Đây là đoạn minh họa **nằm trong cùng test hoặc service**, nơi `dn`, `cn` và `ldapTemplate` đã có giá trị; cần import `java.util.List`, `LdapQuery`, `LdapQueryBuilder` tương ứng.

Hai đường kiểm tra **không giống nhau về ngữ nghĩa**:

- `lookup(Name)` đọc entry ở DN cụ thể, không phải tìm mọi entry có `cn` bằng giá trị đó.
- `search(...)` đánh giá filter theo matching rule, base/scope và ACL, nên có thể trả 0, 1 hoặc nhiều entry.
- Nếu server có normalize Unicode hoặc so khớp `cn` không phân biệt hoa/thường, việc query trả entry không chứng minh raw String và DN string giống từng byte.

Không lấy một entry bất kỳ trong kết quả search làm kết luận danh tính khi có nhiều kết quả; nếu cần định danh ổn định, sử dụng thuộc tính như `entryUUID`/`objectGUID` phù hợp provider.

### 9.4. Kiểm thử rename/Modify DN

Đổi RDN là một phép **Modify DN**, khác với update thuộc tính `cn`:

~~~java
Name oldDn = LdapNameBuilder.newInstance("ou=dn-test")
        .add("cn", "Mai, Nguyễn").build();
Name newDn = LdapNameBuilder.newInstance("ou=dn-test")
        .add("cn", "Mai+Nguyễn").build();

// Chỉ gọi khi oldDn là entry TEST đang tồn tại,
// newDn chưa tồn tại và ACL cho phép rename.
ldapTemplate.rename(oldDn, newDn);
~~~

Đoạn code là minh họa cho thao tác trong **directory test**; không chạy nguyên văn nếu chưa tạo entry nguồn. Trong integration test hoàn chỉnh, xác minh:

1. Trước rename, lookup oldDn thành công.
2. Sau rename, lookup newDn thành công và trả entry phù hợp.
3. Lookup oldDn không còn chỉ tới cùng entry như trước (tùy referral/alias policy).
4. Các thuộc tính RDN và stable ID có hành vi đúng với server.
5. Cleanup thực hiện ở **DN mới** sau khi rename thành công, kể cả khi test assertion thất bại.

Directory có thể từ chối rename hoặc có quy tắc quản lý RDN riêng. Không tự kết luận Spring LDAP sẽ cập nhật mọi group membership hoặc các hệ ngoài LDAP tham chiếu DN cũ.

## 10. LDAP server và Unicode normalization: test theo nguồn có thẩm quyền

### 10.1. Test trên máy chủ thật

Với hai giá trị `NFC` và `NFD` của cùng tên hiển thị:

1. Chỉ trong OU test, tạo entry với giá trị được chọn theo chính sách hiện có.
2. Lookup bằng **DN thực** và đọc lại `cn`.
3. Tìm bằng filter `(cn=...)` với NFC rồi NFD, dùng query builder.
4. Ghi nhận server có trả cùng entry hay không, và attribute đọc lại có bị chuẩn hóa không.
5. Lặp lại trên từng provider được hỗ trợ; không suy hành vi từ một LDAP server sang tất cả server.

Không đồng thời tạo hai entry có DN khác nhau chỉ bởi normalization rồi cho rằng directory bắt buộc coi chúng là độc lập. Directory có thể phát hiện trùng dựa trên matching rule/canonicalization riêng. Kiểm thử phải quan sát hành vi thực tế và dọn sạch dữ liệu test.

### 10.2. DN không phải stable ID của người dùng

Nếu `cn=Mai\, Nguyễn,ou=people` được rename thành `cn=Mai Nguyen,ou=people`, DN đổi nhưng thực thể có thể vẫn là cùng người. Vì vậy:

- **Không dùng DN string đã escape** làm khóa liên kết bất biến giữa LDAP và database nếu còn yêu cầu rename/move.
- Với directory hỗ trợ RFC 4530, cân nhắc `entryUUID`; với Active Directory, cân nhắc `objectGUID` nhưng phải chuyển đúng 16 byte nhị phân.
- Khi dùng repository/ODM, `@Id Name dn` thể hiện **DN trong directory**, không phải một ID tự tăng hay stable business ID.
- Khi so sánh dữ liệu giữa hai server, cần namespace nguồn và quy tắc đồng bộ/replication phù hợp.

## 11. Kiểm thử kết hợp Spring Data LDAP ODM và Repository

Trong Spring Data LDAP, entity thường có DN qua `@Id` và có thể dùng `@DnAttribute` để ánh xạ RDN:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
        base = "ou=dn-test",
        objectClasses = {
                "top", "person", "organizationalPerson", "inetOrgPerson"
        })
public class TestPersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    @DnAttribute(value = "cn", index = 0)
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public TestPersonEntry() {}

    // Getters, setters và constructor theo dự án.
}
~~~

Đối với entity trên, **không gán DN từ chuỗi nối thủ công**. Khi cần tạo entity mới, kiểm tra cách ODM tính DN từ `@DnAttribute(index=0)`, trạng thái `@Id` và `@Entry.base` theo phiên bản Spring Data LDAP. Khi đọc một entry đã tồn tại, xác minh:

| Tình huống | Điều cần assert |
| --- | --- |
| `cn` chứa dấu phẩy. | `commonName` trả đúng giá trị raw; `dn` vẫn có RDN hợp lệ. |
| `cn` chứa dấu cộng. | Được ánh xạ thành một `cn` string, không bị hiểu là RDN đa trị. |
| `cn` có Unicode. | ODM không làm mất dấu hoặc đổi encoding ngoài chính sách. |
| Entry bị rename. | DN trên entity đọc lại phản ánh tên mới; không lấy cache cũ làm định danh. |
| `@Id` bị gán DN sai trước `save`. | Không tạo/ghi sang OU khác; repository không được coi là cơ chế kiểm soát authorization. |
| Field ngoài schema không được ghi. | Server/ACL từ chối đúng; test bảo toàn attribute khác. |

**Đặc biệt:** `LdapRepository.save(entity)` không nên bị hiểu là một upsert tự động dựa trên sự tồn tại thực tế của entry. Trong nhiều cách triển khai, DN/`@Id` đã có khiến object được coi là existing; nếu muốn thử create trên entity mới phải thiết kế `@DnAttribute`/newness đúng. Các test DN có ký tự đặc biệt phải kết hợp với kiểm thử create/update của repository nếu ứng dụng thật sử dụng ODM để ghi dữ liệu.

## 12. Kiểm thử LDIF và công cụ dòng lệnh

### 12.1. DN trong LDIF

LDIF dùng một dạng biểu diễn khác với Java `LdapName.toString()`. Đặc biệt, giá trị DN có ký tự không thuộc ASCII có thể cần biểu diễn **Base64** trên dòng `dn::`.

Ví dụ ASCII có dấu phẩy trong **giá trị cn**, escape theo DN string:

~~~ldif
dn: cn=Mai\, Nguyen,ou=dn-test,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
cn: Mai, Nguyen
sn: Test
~~~

Với tên `Nguyễn` có dấu, sử dụng công cụ xuất LDIF đáng tin cậy hoặc tạo Base64 đúng theo RFC 2849, **không** tự thay dấu tiếng Việt bằng dấu hỏi hoặc xóa dấu để ép file về ASCII. Dòng `dn::` chứa Base64 của **toàn bộ DN string đã biểu diễn đúng**, khác với việc escape RDN.

### 12.2. Kiểm tra `ldapsearch`

Trong directory test được cấp quyền:

~~~bash
ldapsearch -LLL -x \
  -H "ldaps://ldap-test.example.org:636" \
  -D "cn=lab-reader,ou=services,dc=example,dc=org" -W \
  -b "ou=dn-test,dc=example,dc=org" -s one \
  "(objectClass=inetOrgPerson)" dn cn sn
~~~

Quan sát DN server trả về và so sánh với kết quả `LdapTemplate.lookup(...)`. `-W` đọc mật khẩu tương tác; không đưa secret thẳng vào command line. Nếu công cụ CLI và Java khác kết quả, kiểm tra base/scope, account bind, ACL, TLS, projection và Unicode matching rule.

Đối với lookup theo DN chính xác, phải đưa DN có cấu trúc/escape hợp lệ và **quote đúng trong shell**. Shell quoting chỉ bảo vệ trình thông dịch lệnh, **không thay** RFC 4514 hoặc RFC 4515.

## 13. Ma trận kiểm thử chấp nhận

| Nhóm | Dữ liệu hoặc thao tác | Kỳ vọng |
| --- | --- | --- |
| Dấu phẩy | `Mai, Nguyễn`. | RDN `cn` chứa đúng giá trị; base không đổi. |
| Dấu cộng | `An+Minh`. | Một giá trị cn, không tự thành multi-valued RDN. |
| Dấu bằng | `QA=Automation`. | Không tách thành cặp attribute mới. |
| Gạch chéo ngược | `An\Bình`. | Parse lại giữ nguyên dấu gạch chéo ngược gốc. |
| Nháy kép/chấm phẩy | `"Mai"`, `An;Minh`. | Round-trip thành công hoặc lý do server từ chối được ghi nhận rõ. |
| `#` đầu giá trị | `#Thủy`. | Không thành dạng hex RDN ngoài ý muốn. |
| Khoảng trắng | ` Lan`, `Lan `. | Bảo toàn hoặc từ chối theo policy; không tự trim. |
| Unicode tiếng Việt | `Đặng Thị Mỹ`. | JNDI round-trip đúng và integration test đọc lại đúng. |
| Unicode ngoài Latin | `李小龍`. | Unit test parser không giả định ASCII. |
| Unicode ngoài BMP | `Nguyễn 👩‍💻`. | Không mất code point; server có thể áp policy riêng. |
| NFC/NFD | Cùng tên hiển thị theo hai cách biểu diễn. | Ghi nhận rõ normalization policy và server matching. |
| Chuỗi giống DN | `cn=Admin,ou=services` làm giá trị cn. | Không thay đổi số RDN/base nhờ builder. |
| Filter injection | `Mai*(Nguyễn)`. | Dùng filter builder; dấu `*`/`(`/`)` là literal. |
| Control characters | Null, CR, LF, surrogate lẻ. | Bị validation từ chối theo policy ứng dụng. |
| Base sai | DN bị ghép lặp `dc=example,dc=org`. | Test phát hiện lookup sai; không tự sửa bằng cách bỏ escape. |
| Rename DN | Đổi tên trong OU test. | DN mới tìm được; cleanup đúng DN; không bỏ sót entry. |
| ACL thiếu | Account không được read/create. | Phân biệt thiếu quyền với dữ liệu không tồn tại. |
| Schema sai | Thiếu `sn` cho `person`. | Server từ chối; không báo DN escape lỗi nếu thực tế là schema. |

### 13.1. Phân loại test để tiết kiệm công sức

- **Unit test:** kiểm tra cú pháp `LdapNameBuilder`, `Rdn`, escaping và Unicode normalization, chạy nhanh không cần server.
- **Integration test:** kiểm tra `bind`, `lookup`, `search`, `rename`/`unbind`, schema/ACL, TLS và tính nhất quán dữ liệu trên directory test.
- **Compatibility test:** lặp cùng bộ mẫu trên những LDAP server được hỗ trợ; không suy hành vi OpenLDAP cho Active Directory hoặc ngược lại.
- **Security test:** kiểm tra caller HTTP không được tự chọn base DN/attribute/scope, không thực hiện thao tác ghi bằng account read-only, không lộ DN nhạy cảm hoặc PII qua log.

Đừng xem một unit test `Rdn.escapeValue` thành công là đủ để khẳng định Java, server, hệ thống quản lý user và database đã đồng ý về cùng một định danh.

## 14. Chẩn đoán lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra / sửa |
| --- | --- | --- |
| `InvalidNameException` khi DN có dấu phẩy. | Nối string thô, thiếu escape đúng ngữ cảnh. | Dùng `LdapNameBuilder.add("cn", value)`; unit test số RDN. |
| Tên có dấu cộng bị tách thành RDN đa trị. | Dùng `cn=An+Minh` không escape. | Dùng `Rdn`/builder; test `getValue()`. |
| Tên bị mất khoảng trắng đầu/cuối. | Code gọi `trim`/`strip` ngoài chính sách. | Định nghĩa policy rõ, kiểm thử raw value. |
| Unicode hiển thị giống nhưng lookup fail. | NFC/NFD, matching rule, DN cũ hoặc khác code point. | Log/so sánh code point có bảo vệ PII trong test, kiểm tra DN thực. |
| Mojibake/dấu hỏi. | Sai charset khi tạo LDIF hoặc đọc dữ liệu ngoài Java. | UTF-8 cho nội dung text, Base64 LDIF khi quy tắc yêu cầu. |
| Filter trả nhiều kết quả bất thường. | Ghép input vào filter hoặc dùng wildcard sai. | `LdapQueryBuilder.where(...).is(value)`. |
| Lookup đọc sai OU. | DN tương đối và context base bị ghép sai. | Kiểm tra `spring.ldap.base` và DN thực. |
| LDAP code **32** (`noSuchObject`). | DN không tồn tại, rename, base hoặc ACL đặc thù. | Xác minh bằng cùng account, không kết luận ngay Unicode lỗi. |
| LDAP code **50** (`insufficientAccessRights`). | Account không được phép tìm/đọc/ghi. | Kiểm tra ACL server, không thử chuyển sang admin tùy tiện. |
| LDAP code **65** (`objectClassViolation`). | Thiếu field bắt buộc hoặc schema không khớp. | Kiểm tra `objectClass`/`cn`/`sn`. |
| Rename thành công nhưng cleanup fail. | Test vẫn dùng old DN. | Theo dõi DN đích và cleanup ở vị trí thật. |
| Dữ liệu trùng sau migration. | Dùng DN string/username làm stable ID; normalization thay đổi. | Dùng stable ID theo provider và quy trình reconciliation. |

## 15. Bài tập thực hành

Một directory thử nghiệm có `spring.ldap.base=dc=company,dc=internal` và OU `ou=dn-test`. Ứng dụng cần tạo các entry `inetOrgPerson` với `cn` là:

~~~text
1.  Mai, Nguyễn
2.  An+Minh
3.  QA=Automation
4.  "Thúy"
5.  #Hà
6.   Lan
7.  Lan␠                (ký hiệu ␠ là một khoảng trắng cuối)
8.  Đặng Thị Mỹ
9.  李小龍
10. Nguyễn 👩‍💻
~~~

**Yêu cầu:**

1. Giải thích tại sao ghép `"cn=" + value + ",ou=dn-test"` là sai với một số giá trị trên.
2. Viết hàm `personDn(value)` bằng `LdapNameBuilder.newInstance(...).add("cn", value).build()`.
3. Viết `@ParameterizedTest` để khẳng định tổng số RDN đúng, giá trị `Rdn.getValue()` không đổi và parse lại thành công.
4. Phân biệt `cn=An\+Minh` với `cn=An+uid=Minh`.
5. Tạo hai chuỗi NFC/NFD của `Nguyễn` bằng `Normalizer` và xác minh chúng có thể khác bytes.
6. Viết validation từ chối ký tự điều khiển mà **không tự xóa** dấu phẩy, dấu cộng hoặc dấu tiếng Việt.
7. Viết test `LdapTemplate.bind`/`lookup` trên OU test, bảo đảm cleanup ngay cả khi assertion fail.
8. Dùng `LdapQueryBuilder.where("cn").is(value)` tìm entry; vì sao kết quả search không nhất thiết tương đương lookup theo DN?
9. Thiết kế test rename `cn=Mai\, Nguyễn` sang `cn=Mai\+Nguyễn` mà không để sót entry sau test.
10. Nêu cách phân biệt lỗi DN syntax, lỗi schema, lỗi ACL và lỗi Unicode matching trên directory thực.

**Gợi ý đáp án:**

- Các ký tự `,` và `+` không escape có thể thay đổi cấu trúc DN; phải đưa chúng vào builder như **giá trị RDN**, không như chuỗi DN thô.
- Unit test kiểm tra `getRdn(size-1).getValue()` và số thành phần; đừng chỉ so sánh `toString()`.
- `cn=An\+Minh` là một giá trị `cn=An+Minh`, còn `cn=An+uid=Minh` là RDN đa trị.
- NFC/NFD khác cách biểu diễn code point/UTF-8; muốn normalize tên mới phải có policy và test matching rule server.
- Kiểm thử integration dùng OU riêng, `bind` rồi `lookup`, và cleanup bằng DN thực; không chạy trên production.
- Search theo `cn` đánh giá matching rule/filter và có thể trả nhiều entry; lookup theo `Name` đọc một vị trí DN cụ thể.
- Đổi RDN là thao tác rename/Modify DN; xác nhận DN mới, quyền, schema và tham chiếu trước khi coi test đạt.

## 16. Ghi nhớ

**DN có ký tự đặc biệt và Unicode phải được kiểm thử ở cả hai tầng: Java/JNDI và directory thực.** Dùng `LdapNameBuilder` hoặc `Rdn` thay cho phép nối chuỗi; kiểm tra round-trip giá trị gốc, RDN count và base; dùng `LdapQueryBuilder` riêng cho **filter values**. Unicode NFC/NFD là một chính sách dữ liệu và matching rule, không đơn thuần là vấn đề escape.

Trong Spring Data LDAP, DN còn gắn với `@Id`/`@DnAttribute`, repository, rename và CRUD. Hãy xây ma trận unit test + integration test với OU riêng, schema/ACL đúng, TLS, test cleanup có kiểm soát và stable ID theo provider khi cần đồng bộ. Một DN string “trông đúng” không đủ: cần kiểm tra cấu trúc tên, giá trị thuộc tính và hành vi server.

### Tài liệu tham khảo

- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515)
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512)
- [RFC 2849 — LDAP Data Interchange Format (LDIF)](https://www.rfc-editor.org/rfc/rfc2849)
- [Spring LDAP — Distinguished Names](https://docs.spring.io/spring-ldap/reference/basic.html)
- [Spring LDAP — Query Builder](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/)
- [Java SE — LdapName](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/LdapName.html)
- [Java SE — Rdn](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/ldap/Rdn.html)
- [Java SE — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
