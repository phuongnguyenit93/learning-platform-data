# Đọc thuộc tính đơn trị, đa trị và xử lý thuộc tính bắt buộc bị thiếu

## 1. Tại sao cần kiểm tra thuộc tính SAML?

Khi **Service Provider (SP)** dùng Spring Security SAML2 đăng nhập với **Identity Provider (IdP)**, một SAML Assertion có thể chứa các thuộc tính danh tính và tổ chức như **employeeId, email, displayName, groups, department, costCenter**. Sau khi Spring Security/OpenSAML xác thực SAMLResponse, ứng dụng cần đọc các thuộc tính này để liên kết tài khoản, hiển thị profile và phân quyền nghiệp vụ.

Tuy nhiên, SAML cho phép một **Attribute có nhiều AttributeValue**. Từ góc nhìn ứng dụng:

- Một trường được kỳ vọng **đơn trị** có thể bị thiếu, có hai giá trị mâu thuẫn, chứa giá trị rỗng hoặc kiểu không tương thích.
- Một trường **đa trị** có thể là danh sách nhóm, vai trò, đơn vị hoặc entitlement; danh sách có thể rỗng, lặp hoặc chứa phần tử sai kiểu.
- Một trường **bắt buộc** để liên kết tài khoản có thể không được IdP phát hành do mapping, quyền riêng tư, thay đổi schema hay chính sách tenant.
- Việc đăng nhập SAML thành công **không đảm bảo** mọi attribute nghiệp vụ cần thiết đều tồn tại hoặc hợp lệ.
- Các thao tác lấy “giá trị đầu tiên” hoặc gán “quyền mặc định” khi attribute thiếu có thể dẫn tới **liên kết nhầm danh tính hoặc cấp quyền sai**.

**Trọng tâm:** đọc từ **Saml2AuthenticatedPrincipal** sau khi SAML đã được xác minh; phân biệt optional/required, single/multi; kiểm tra kiểu, giá trị, số lượng và nguồn tin cậy; xử lý thiếu dữ liệu theo nguyên tắc **fail closed** ở tầng phù hợp.

Ví dụ dùng **Java 17, Spring Boot 3.3.5 và Spring Security 6.x**. Những chi tiết Spring Security 7.x có thể khác, vì API SAML đã thay đổi; cần đối chiếu Javadoc theo phiên bản thật.

## 2. Cấu trúc AttributeStatement và AttributeValue

Đây là fragment XML minh họa, **không phải Assertion đầy đủ/đã ký**:

~~~xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">

  <saml:Attribute Name="employeeId">
    <saml:AttributeValue>EMP-041</saml:AttributeValue>
  </saml:Attribute>

  <saml:Attribute Name="groups">
    <saml:AttributeValue>team-java</saml:AttributeValue>
    <saml:AttributeValue>team-ops</saml:AttributeValue>
  </saml:Attribute>

  <saml:Attribute Name="displayName"
      FriendlyName="Display name">
    <saml:AttributeValue>Nguyễn An</saml:AttributeValue>
  </saml:Attribute>

</saml:AttributeStatement>
~~~

Bản XML được phát hành thật còn cần Response, Assertion, Issuer, chữ ký, Subject/NameID, Conditions và những phần tử khác theo giao thức. **Không dùng fragment này để đăng nhập hoặc thay thế kiểm chứng chữ ký.**

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Subject/NameID** | Định danh subject do IdP phát hành. **Không phải một SAML Attribute tên employeeId hoặc email**; tính ổn định tùy NameID format và hợp đồng IdP. |
| **AttributeStatement** | Một nhóm thuộc tính trong Assertion; có thể có nhiều thuộc tính. |
| **Attribute.Name** | Khóa chuẩn để nhận diện SAML Attribute, có thể là tên ngắn hoặc URN/OID. |
| **Attribute.FriendlyName** | Nhãn đọc cho con người; không dùng thay Attribute.Name để bảo đảm nhận diện. |
| **Attribute.NameFormat** | Dạng của Name, ví dụ basic, URI hoặc unspecified. |
| **AttributeValue** | Giá trị dữ liệu; có thể có **0, 1 hoặc nhiều giá trị** và kiểu không nhất thiết là String. |
| **EncryptedAttribute** | Thuộc tính được mã hóa; cần SP decryption credentials phù hợp trước khi đọc. |

Những tên như **email**, **mail**, **urn:oid:0.9.2342.19200300.100.1.3** hay **http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress** đều có thể đại diện cho thông tin email ở các IdP khác nhau. Spring Security **không tự đổi mọi tên này thành email**. Hợp đồng IdP phải xác định **Attribute.Name thực tế**, NameFormat khi có ý nghĩa, kiểu, cardinality và điều kiện phát hành.

### Multi-value không phải CSV

Một Attribute có hai phần tử **AttributeValue** khác với một AttributeValue chứa **"team-java,team-ops"**. Không tự split theo dấu phẩy trừ khi IdP và SP đã thỏa thuận rõ CSV/custom format.

## 3. Spring Security 6.x chuyển thuộc tính thành principal ra sao?

Trong Servlet SAML2 login, luồng tổng quát là:

~~~text
Browser POST SAMLResponse
  -> Saml2WebSsoAuthenticationFilter
  -> AuthenticationManager / OpenSAML authentication provider
  -> kiểm chữ ký, issuer, destination, audience, time,
     SubjectConfirmation, Recipient, InResponseTo, replay policy
  -> giải mã Assertion/Attribute nếu cần
  -> trích AttributeStatement thành Map<String, List<Object>>
  -> tạo Saml2Authentication + Saml2AuthenticatedPrincipal
  -> SecurityContext của ứng dụng
~~~

Chỉ **sau** khi các bước kiểm chứng hợp lệ, ứng dụng mới dùng principal cho nghiệp vụ.

Các API của **Saml2AuthenticatedPrincipal** trong Spring Security 6.x:

| API | Giá trị trả về | Cách dùng đúng |
| --- | --- | --- |
| **getName()** | String tên principal, thường lấy NameID theo provider mặc định. | Không tự coi là employeeId/email ổn định. |
| **getAttributes()** | **Map<String, List<Object>>**. | Ưu tiên cho kiểm tra chặt kiểu và cardinality. |
| **getAttribute(name)** | Generic **List<A>**, có thể **null** nếu thuộc tính không có. | Dùng cho multi-value khi biết chắc kiểu từ IdP. |
| **getFirstAttribute(name)** | Generic **A**, có thể **null** khi không có. | Chỉ tiện khi biết hợp đồng thực sự bảo đảm đơn trị. |
| **getRelyingPartyRegistrationId()** | String registrationId của quan hệ SP–IdP. | Giúp chọn schema/mapping theo đối tác đã xác thực. |

Ví dụ đọc nhanh sau SAML login:

~~~java
// Chỉ là đoạn code minh họa, nằm trong controller có principal hợp lệ
String displayName = principal.getFirstAttribute("displayName");
List<String> groups = principal.getAttribute("groups");
~~~

**Giới hạn:** getFirstAttribute chỉ lấy **phần tử đầu**, không kiểm tra danh sách có hai giá trị. getAttribute dùng generic nhưng không kiểm tra từng **Object** ở runtime. Nếu IdP gửi nhóm dưới kiểu không phải String, việc lặp một List<String> có thể gây ClassCastException. Đối với mã định danh hoặc quyền, nên dùng **getAttributes()** và xác minh phần tử qua **instanceof String**.

Với Spring Security 7.x, một số API SAML principal cũ được đánh dấu deprecated và thay bằng accessor/authentication model mới; bài này cố ý dùng **Security 6.x**.

## 4. Chính sách rõ ràng cho bốn loại thuộc tính

| Loại | Ví dụ | Thiếu / rỗng | Có nhiều / sai kiểu |
| --- | --- | --- | --- |
| **Optional single** | displayName | Có thể dùng Optional.empty hoặc nhãn hiển thị mặc định. | Nên báo lỗi contract, không âm thầm lấy giá trị đầu nếu sai cardinality. |
| **Required single** | stableSubjectId, employeeId | **Từ chối** liên kết tài khoản/chức năng cần định danh. | **Từ chối** vì ambiguous hoặc type invalid. |
| **Optional multi** | groups dùng cho thông tin hiển thị | Có thể trả danh sách rỗng; **không tự cấp quyền**. | Kiểm từng phần tử; loại trùng chỉ khi policy cho phép. |
| **Required multi** | ít nhất một mã entitlement cần thiết | **Từ chối** chức năng yêu cầu membership. | Kiểm từng phần tử và allowlist; không chấp nhận giá trị lạ. |

Trường hợp **required single** phải phân biệt:

- **MISSING:** map không có khóa.
- **EMPTY:** khóa tồn tại nhưng list rỗng, chuỗi rỗng hoặc trắng.
- **CARDINALITY:** map có từ hai giá trị trở lên dù mỗi giá trị có vẻ đúng.
- **TYPE:** một giá trị không thuộc kiểu đã thỏa thuận (ví dụ Integer thay String).
- **FORMAT:** một String có kiểu ký tự, độ dài hoặc định dạng sai contract.
- **TRUST:** thông tin không đến từ IdP/registration được phép, hoặc SAML chưa qua kiểm chứng.

**Không đặt employeeId mặc định thành "guest", tenantId thành "default" hoặc tự chọn giá trị đầu tiên của danh sách.** Nếu thuộc tính ảnh hưởng tới nhận diện/authorization, mọi trường hợp bất thường phải **fail closed**.

### Trường hợp optional không có nghĩa bỏ qua mọi lỗi

Nếu displayName **không có** thì có thể hiển thị “Chưa cung cấp”. Nhưng nếu displayName có **ba giá trị** khi IdP contract chỉ cho phép một, đó là **vi phạm schema**; tùy hệ thống có thể bỏ hiển thị và ghi cảnh báo, hoặc từ chối bước nghiệp vụ. Không được đồng nhất **missing** với **invalid present value** khi quyết định security.

## 5. Thuộc tính đa trị và quyền truy cập

**groups, memberOf, roles, entitlements** thường là đa trị. Một nhóm có thể bị lặp, một IdP có thể giới hạn số nhóm trong Assertion hoặc không release groups cho một số tài khoản.

Ví dụ dữ liệu sau validation:

~~~text
groups = ["team-java", "team-ops", "team-java"]
~~~

Nếu hợp đồng xem groups là **tập membership**, có thể loại trùng và giữ thứ tự đầu tiên. Nếu thứ tự nhóm mang ý nghĩa, không tự thay bằng Set. Không tự lowercase hoặc trim mọi group/identifier khi hợp đồng còn phân biệt hoa-thường hoặc whitespace.

**Phân quyền phải theo allowlist của ứng dụng**:

| Registration đã xác thực | Group trong Assertion | Authority nội bộ có thể cấp |
| --- | --- | --- |
| corp | app-reports-view | REPORT_READ |
| corp | app-reports-edit | REPORT_WRITE |
| partner | app-reports-view | Không tự cấp nếu chính sách partner chưa cho phép |
| Bất kỳ | admin, superuser hoặc giá trị lạ | Không tự tạo ROLE_ADMIN |

Không đưa mọi giá trị từ IdP trực tiếp vào **SimpleGrantedAuthority("ROLE_" + value)** nếu chưa thỏa thuận danh sách được phép và tenant. Nếu groups **thiếu**, mặc định không có quyền tương ứng; không giả định rằng thiếu groups nghĩa là user thuộc mọi nhóm.

**getAttributes() không phải dữ liệu luôn mới:** sau khi SP tạo local HttpSession, attributes phản ánh Assertion tại thời điểm đăng nhập. Nếu nhóm/role bị IdP thu hồi giữa phiên, ứng dụng cần chính sách session lifetime, reauthentication, synchronization hoặc kiểm soát quyền phía server thích hợp. Không tuyên bố rằng IdP thay nhóm là mọi phiên SP cập nhật lập tức.

## 6. Thiết kế lớp kiểm dữ liệu Java 17 độc lập

Dùng lớp **AttributeReader** nhận chính kiểu **Map<String, List<Object>>**. Lớp có thể kiểm phần tử String, cardinality và blank, phân loại nguyên nhân mà **không rò rỉ giá trị nhạy cảm**. Đây là công cụ đọc thuộc tính **sau SAML validation**, **không** xác minh chữ ký hoặc xử lý raw SAMLResponse.

### 6.1. AttributeReader.java

Tạo file **src/main/java/com/example/samlattrs/AttributeReader.java**:

~~~java
package com.example.samlattrs;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public final class AttributeReader {
    private final Map<String, List<Object>> attributes;

    public AttributeReader(Map<String, List<Object>> attributes) {
        this.attributes = Objects.requireNonNull(attributes, "attributes");
    }

    public String requiredSingle(String name) {
        List<Object> values = attributes.get(name);
        if (values == null) {
            throw new AttributeProblem("MISSING", name);
        }
        if (values.isEmpty()) {
            throw new AttributeProblem("EMPTY", name);
        }
        if (values.size() != 1) {
            throw new AttributeProblem("CARDINALITY", name);
        }
        return nonBlankString(values.get(0), name);
    }

    public Optional<String> optionalSingle(String name) {
        List<Object> values = attributes.get(name);
        if (values == null || values.isEmpty()) {
            return Optional.empty();
        }
        if (values.size() != 1) {
            throw new AttributeProblem("CARDINALITY", name);
        }
        Object raw = values.get(0);
        if (!(raw instanceof String value)) {
            throw new AttributeProblem("TYPE", name);
        }
        String normalized = value.strip();
        return normalized.isEmpty()
                ? Optional.empty() : Optional.of(normalized);
    }

    public List<String> optionalMany(String name) {
        List<Object> values = attributes.get(name);
        if (values == null || values.isEmpty()) {
            return List.of();
        }

        LinkedHashSet<String> distinct = new LinkedHashSet<>();
        for (Object raw : values) {
            distinct.add(nonBlankString(raw, name));
        }
        return List.copyOf(distinct);
    }

    public List<String> requiredMany(String name) {
        List<String> values = optionalMany(name);
        if (values.isEmpty()) {
            String code = attributes.containsKey(name) ? "EMPTY" : "MISSING";
            throw new AttributeProblem(code, name);
        }
        return values;
    }

    private static String nonBlankString(Object raw, String name) {
        if (!(raw instanceof String value)) {
            throw new AttributeProblem("TYPE", name);
        }
        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new AttributeProblem("EMPTY", name);
        }
        return normalized;
    }

    public static final class AttributeProblem extends IllegalArgumentException {
        private final String code;

        public AttributeProblem(String code, String name) {
            super("Invalid SAML attribute " + name + " (" + code + ")");
            this.code = code;
        }

        public String code() {
            return code;
        }
    }
}
~~~

### Giải thích các quyết định

1. **Map<String, List<Object>>** phản ánh API Spring 6.x, không ép kiểu cả List.
2. **requiredSingle** đòi đúng một giá trị String không rỗng, tránh chọn bừa.
3. **optionalSingle** cho phép vắng mặt nhưng vẫn báo lỗi nếu giá trị hiện diện có kiểu/cardinality không đúng.
4. **optionalMany** trả List.of() khi vắng mặt; với dữ liệu có mặt phải kiểm từng phần tử.
5. **LinkedHashSet** loại trùng và giữ thứ tự đầu tiên; chỉ dùng khi nghiệp vụ xem values là membership set.
6. **AttributeProblem.code()** cho phép log mã lỗi thay vì log raw attribute values.
7. **strip()** là quy tắc minh họa; chỉ áp dụng nếu hợp đồng định danh cho phép bỏ khoảng trắng hai đầu. Với mã định danh có whitespace mang ý nghĩa, phải đổi quy tắc.
8. Code chưa áp dụng regex/độ dài tối đa/allowlist; cần bổ sung theo schema trước production.

### 6.2. Chương trình kiểm thử không cần Spring hoặc IdP

Lưu **src/main/java/com/example/samlattrs/AttributeReaderDemo.java**:

~~~java
package com.example.samlattrs;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AttributeReaderDemo {
    public static void main(String[] args) {
        Map<String, List<Object>> values = new LinkedHashMap<>();
        values.put("employeeId", List.of("EMP-041"));
        values.put("groups", List.of("team-java", "team-ops", "team-java"));
        values.put("email", List.of("a@example.org", "b@example.org"));
        values.put("quota", List.of(42));
        values.put("emptyValue", List.of());

        AttributeReader reader = new AttributeReader(values);

        System.out.println("employeeId=" +
                reader.requiredSingle("employeeId"));
        System.out.println("groups=" + reader.optionalMany("groups"));
        System.out.println("department=" +
                reader.optionalSingle("department").orElse("(missing)"));

        printError("email", () -> reader.requiredSingle("email"));
        printError("emptyValue",
                () -> reader.requiredSingle("emptyValue"));
        printError("quota", () -> reader.requiredSingle("quota"));
        printError("unknown", () -> reader.requiredSingle("unknown"));
    }

    private static void printError(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=VALID");
        }
        catch (AttributeReader.AttributeProblem ex) {
            System.out.println(label + "=" + ex.code());
        }
    }
}
~~~

Chạy JDK 17+ từ thư mục gốc project:

~~~bash
javac -d out src/main/java/com/example/samlattrs/AttributeReader.java src/main/java/com/example/samlattrs/AttributeReaderDemo.java
java -cp out com.example.samlattrs.AttributeReaderDemo
~~~

**stdout chính xác:**

~~~text
employeeId=EMP-041
groups=[team-java, team-ops]
department=(missing)
email=CARDINALITY
emptyValue=EMPTY
quota=TYPE
unknown=MISSING
~~~

Trường **email** có hai giá trị nên trả **CARDINALITY**; không chọn địa chỉ đầu tiên. **quota** có Integer thay String nên **TYPE**; không chuyển tự động thành "42". **unknown** thiếu key và **emptyValue** có list rỗng là hai tình huống khác nhau. **department** optional nên được phép vắng. **groups** được loại trùng theo chính sách minh họa. Demo không xác minh chữ ký SAML và không có khả năng đăng nhập IdP.

### Mở rộng validation theo hợp đồng

- Với **email**, chỉ parse/normalize sau khi quyết định email có phải chỉ để liên hệ hay để liên kết account; không mặc định coi email là immutable global ID.
- Với **employeeId**, bổ sung quy tắc format, độ dài, tính duy nhất theo issuer và tài khoản active.
- Với **groups**, thêm maximum number of values và allowlist theo registration; không cấp quyền cho group lạ.
- Với **Date/Integer/Boolean**, định nghĩa phép chuyển kiểu cụ thể, bắt lỗi parse; không dùng **String.valueOf** như giải pháp chung.
- Với Unicode, quyết định rõ normalization và case sensitivity; không tự chuyển chữ hoa/chữ thường của mã định danh.
- Với dữ liệu nhạy cảm, log **tên field và mã lỗi**, không log giá trị thuộc tính thật.

## 7. Ví dụ Spring Boot 3.3.5 đọc principal sau SAML login

Ứng dụng sau là **Spring SAML2 Service Provider** có một IdP registration. Nó chỉ chạy đủ luồng login khi IdP thật đã đăng ký **SP entityID, ACS và certificate/trust**, và phát attributes đúng contract.

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>saml-attributes-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots><enabled>false</enabled></snapshots>
        </repository>
    </repositories>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-saml2-service-provider</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: ${SAML_IDP_METADATA_URI}

server:
  port: 8080
~~~

**SAML_IDP_METADATA_URI** là biến môi trường chứa URL metadata IdP thật, đã được tổ chức phê duyệt. Để đăng nhập, cần IdP thực tế cùng SP entityID/ACS và trust khớp; ví dụ này không cung cấp IdP hoặc tự phát hành Assertion.

### 7.3. Ứng dụng và cấu hình bảo mật

**src/main/java/com/example/samlattrs/SamlAttributesApplication.java**

~~~java
package com.example.samlattrs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlAttributesApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlAttributesApplication.class, args);
    }
}
~~~

**src/main/java/com/example/samlattrs/SecurityConfig.java**

~~~java
package com.example.samlattrs;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Lưu ý:** Spring Security tự xử lý callback **/login/saml2/sso/{registrationId}**. Không viết controller nhận SAMLResponse để parse thủ công.

### 7.4. Controller sử dụng AttributeReader

**src/main/java/com/example/samlattrs/ProfileController.java**

~~~java
package com.example.samlattrs;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {
    @GetMapping("/")
    public String home() {
        return "SAML attributes SP ready";
    }

    @GetMapping("/account")
    public Map<String, Object> account(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        if (principal == null) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "Authentication required");
        }

        AttributeReader reader = new AttributeReader(principal.getAttributes());

        try {
            String employeeId = reader.requiredSingle("employeeId");
            List<String> groups = reader.optionalMany("groups");
            String displayName = reader.optionalSingle("displayName")
                    .orElse("Unknown");

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("employeeId", employeeId);
            result.put("displayName", displayName);
            result.put("groups", groups);
            return result;
        }
        catch (AttributeReader.AttributeProblem problem) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Required identity data is unavailable");
        }
    }
}
~~~

Dùng lớp **AttributeReader.java** đã tạo ở phần 6, cùng package **com.example.samlattrs**.

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

**Kết quả có thể kiểm tra:**

- **GET http://localhost:8080/** trả đúng body **SAML attributes SP ready**.
- **GET http://localhost:8080/account** khi chưa xác thực kích hoạt SAML login nếu IdP registration hợp lệ.
- Sau IdP đăng nhập và gửi Assertion hợp lệ có **employeeId, groups, displayName** là String, endpoint trả JSON như:

~~~json
{
  "employeeId": "EMP-041",
  "displayName": "Nguyễn An",
  "groups": ["team-java", "team-ops"]
}
~~~

- Nếu **employeeId thiếu/rỗng/đa trị/sai kiểu**, controller trả **403** theo policy. Với groups thiếu, trả **[]**, không suy ra quyền admin. Với displayName thiếu, dùng nhãn hiển thị **Unknown**.
- Không thể bảo đảm NameID, attribute values hay kết quả SSO nếu chưa có IdP thật, certificate/metadata đúng và release policy phù hợp.

**Phân biệt cực kỳ quan trọng:** controller trả **403** vì thiếu required employeeId **không đồng nghĩa SAML login thất bại**. Spring có thể đã tạo local SecurityContext/session hợp lệ. Nếu employeeId là điều kiện **bắt buộc cho toàn ứng dụng**, cần kiểm tra ở thành phần authentication conversion/account provisioning **sau khi SAML đã được xác thực**, và trả authentication failure trước khi cho phép lập phiên ứng dụng tương ứng.

## 8. Required attribute ở login hay ở endpoint?

### Bắt buộc cho liên kết tài khoản

Nếu stableSubjectId/employeeId cần thiết để biết **người dùng này là ai trong hệ thống nội bộ**, các bước nên gồm:

1. Xác minh SAMLResponse theo IdP registration, chữ ký, issuer, time, audience, recipient và response correlation.
2. Xác định schema thuộc tính theo **registrationId/IdP**, tránh trộn lẫn hai tổ chức.
3. Đọc required-single theo exact Attribute.Name.
4. Xác minh String, **size=1**, không blank, định dạng/độ dài theo schema.
5. Liên kết đến local account bằng khóa có **namespace IdP**, chẳng hạn cặp issuer + stable subject; không tự dùng email để gắn tài khoản.
6. Kiểm tra local account active, tenant, lifecycle, deprovisioning và status.
7. Nếu một bước fail, không tạo account/authority mặc định hoặc vô tình tạo guest dùng chung.

Thực thi trước khi cấp danh tính ứng dụng khi policy yêu cầu. Trong Spring Security 6.x, có thể dùng **custom authentication converter sau default SAML validation** hoặc tầng provisioning/hook phù hợp phiên bản; phải bảo toàn mọi validation của framework và kiểm thử rằng lỗi bắt buộc thực sự ngăn login.

### Bắt buộc cho một chức năng

Nếu **costCenter** cần để gửi hóa đơn, user có thể đăng nhập hợp lệ nhưng:

- Không có costCenter -> **không được gửi hóa đơn**, trả 403 theo nghiệp vụ.
- Vẫn có thể xem profile hoặc trang khác không cần costCenter.
- Không tự suy ra costCenter từ email domain hay group.
- Không dùng quyền “mặc định rộng” vì group/costCenter bị thiếu.

Bảo mật tốt là **fail closed đúng nơi**, không nhất thiết khóa toàn bộ ứng dụng nếu chỉ một chức năng cần thêm dữ liệu.

### Metadata RequestedAttribute không thực thi thay ứng dụng

Trong **SPSSODescriptor**, metadata có thể khai báo:

~~~xml
<md:AttributeConsumingService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    index="0">
  <md:ServiceName xml:lang="vi">Ứng dụng nội bộ</md:ServiceName>
  <md:RequestedAttribute Name="employeeId" isRequired="true"/>
</md:AttributeConsumingService>
~~~

Đây là **yêu cầu thuộc tính khi trao đổi metadata**. Không suy luận rằng chỉ nhờ **isRequired=true** IdP chắc chắn phát giá trị hoặc Spring Security mặc định sẽ tự fail login nếu thiếu. Ứng dụng vẫn cần kiểm giá trị **runtime** và thống nhất attribute release policy với IdP.

## 9. Thiết kế nhiều IdP / tenant

Có thể có hai registration:

| Chính sách | IdP corp | IdP partner |
| --- | --- | --- |
| Stable identifier | employeeId | externalSubjectId |
| Email | mail | claims/emailaddress |
| Groups | memberOf | groups |
| Display name | displayName | fullName |
| Mã tenant | corp | partner |

**Không dùng cùng một Attribute.Name trên mọi IdP khi chưa có hợp đồng.** Sau login, lấy registrationId đã được xác thực để chọn mapping theo **allowlist IdP**. Một IdP có thể phát employeeId trùng IdP khác; do đó không dùng employeeId một mình làm primary key xuyên tổ chức.

**Không cho client chưa xác thực quyết định mapping/certificate/metadata URL** qua request parameter như tenant=... nhằm cấp quyền. Dữ kiện issuer hay claim trong SAMLResponse trước validation chỉ là đầu vào chưa tin; phải dựa trên IdP trust configuration và Authentication đã hoàn tất.

Nếu group overage hoặc attribute release policy làm nhóm bị thiếu, coi quyền liên quan là **không được chứng minh**. Phối hợp với IdP/admin và quy trình đồng bộ account, không giả định “thiếu nhóm = có toàn quyền”.

## 10. Kiểm thử đúng các tình huống đơn trị, đa trị và thiếu

Dùng IdP sandbox phát **SAMLResponse hợp lệ được ký** để kiểm từng trường hợp. Nếu chỉnh tay XML đã ký, lỗi signature có thể xảy ra trước bước đọc thuộc tính, không thể kết luận validation nghiệp vụ hoạt động.

| # | Dữ liệu sau SAML validation | Chính sách | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| 1 | employeeId=["EMP-041"] | Required single | Chấp nhận nếu schema/account mapping còn lại hợp lệ. |
| 2 | Không có employeeId | Required single | **MISSING**, từ chối thao tác identity binding. |
| 3 | employeeId=[] | Required single | **EMPTY**. |
| 4 | employeeId=[""] | Required single | **EMPTY**. |
| 5 | employeeId=["  "] | Required single | **EMPTY** theo policy strip. |
| 6 | employeeId=["EMP-041","EMP-042"] | Required single | **CARDINALITY**, không chọn giá trị đầu. |
| 7 | employeeId=[42] | Required String | **TYPE**. |
| 8 | groups=["team-java","team-ops"] | Optional multi | Chấp nhận danh sách đã kiểm kiểu. |
| 9 | Không có groups | Optional multi | Danh sách rỗng; không cấp quyền từ groups. |
| 10 | groups=["team-java","team-java"] | Optional multi set | Loại trùng nếu contract cho phép. |
| 11 | groups=["team-java",42] | Optional multi String | **TYPE**, không coi dữ liệu lạ thành group. |
| 12 | groups=[""] | Required multi | **EMPTY**. |
| 13 | displayName không tồn tại | Optional single | Có thể hiển thị Unknown. |
| 14 | email có 2 giá trị | Expected single | **CARDINALITY**. |
| 15 | IdP đổi mail thành email | Schema mapping | Báo thiếu/contract drift; cần sửa mapping. |
| 16 | IdP A và B cùng employeeId | Multi-IdP binding | Không tự liên kết thành cùng một account. |
| 17 | group lạ "super-admin" | Authorization | Không tự cấp quyền admin. |
| 18 | Response signature sai nhưng có employeeId đẹp | Authentication | Từ chối ở tầng SAML trước khi vào app. |
| 19 | EncryptedAttribute nhưng SP thiếu decryption key | Authentication | Không dùng giá trị chưa giải mã; xử lý SAML error. |
| 20 | NameID có nhưng employeeId thiếu | Required identity | Không thay employeeId bằng NameID không có contract. |
| 21 | costCenter thiếu | Required ở endpoint tài chính | Trả 403 ở endpoint, không nhất thiết hủy login. |
| 22 | Metadata isRequired=true nhưng IdP không release | Contract/runtime | Từ chối chức năng cần nó, liên hệ IdP admin. |

**Negative test đạt** khi hệ thống **từ chối đúng rủi ro**, không phải cố làm mọi trường hợp login được.

Trong unit tests với JUnit 5, bổ sung kiểm chứng **AttributeReader** cho null/missing/empty/blank, sai kiểu, nhiều giá trị, Unicode, giá trị quá dài, dedup, allowlist. Trong integration tests, dùng signed SAMLResponse từ IdP thử nghiệm để bao phủ cả authentication và attribute mapping.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| getFirstAttribute("email") trả null | IdP dùng mail/URN khác hoặc không release. | Đối chiếu Attribute.Name, claim mapping và IdP release policy. |
| getAttribute("groups") trả null | Group attribute thiếu/khác tên/IdP giới hạn groups. | Không tự cấp quyền; kiểm schema và IdP admin. |
| ClassCastException khi xử lý groups | List<Object> có phần tử không phải String. | Duyệt Object và instanceof, không cast mù. |
| /account trả 403 dù SAML login thành công | Required employeeId không đạt contract. | Điều tra schema release; phân biệt business deny với login failure. |
| Hai giá trị employeeId bị chọn nhầm | getFirstAttribute được dùng cho required-single. | Kiểm size==1 và từ chối CARDINALITY. |
| Người dùng nhảy tenant | Liên kết account chỉ bằng email/employeeId không kèm issuer. | Dùng stable subject có namespace IdP/tenant; xác minh local account. |
| Group lạ bất ngờ trở thành ROLE_ADMIN | Mapping trực tiếp mọi group thành authority. | Allowlist per registration, deny by default. |
| SAML validation thất bại trước lúc lấy principal | Signature, issuer, audience, time, subject confirmation, decryption lỗi. | Sửa trust/metadata/cert; không bypass validator. |
| AttributeName thay đổi sau nâng IdP | Schema drift. | Hợp đồng và versioning claim schema, test regression. |
| Metadata isRequired=true nhưng dữ liệu thiếu | Metadata không bắt buộc IdP release runtime tự động. | Kiểm runtime và phối hợp đối tác. |
| Dữ liệu hiển thị có HTML/JS | Attribute được xem như untrusted content ở output. | Escape theo ngữ cảnh render; không đưa vào HTML chưa được bảo vệ. |
| Group change không có hiệu lực ngay | Local SP session lưu attributes tại lúc login. | Đặt policy reauthentication/session sync/revocation tương ứng. |

### Logging và quyền riêng tư

Chỉ log các trường an toàn như **registrationId**, tên thuộc tính đã allowlist, mã lỗi **MISSING/EMPTY/TYPE/CARDINALITY** và correlation ID. Không log raw SAMLResponse, email, employeeId thực, thuộc tính cá nhân, private key hay cookie phiên.

Ví dụ:

~~~text
event=saml_attribute_contract_failed registration=corp attribute=employeeId code=MISSING
~~~

Không trả thông điệp lỗi có giá trị attribute nhạy cảm cho browser. Kết hợp hướng dẫn liên hệ bộ phận quản trị IdP để sửa mapping thay vì nới rule bảo mật.

## 12. Sai lầm phổ biến

1. **getFirstAttribute cho required-single**: chọn một phần tử mà không phát hiện giá trị thứ hai.
2. **Tin generic List<String> là runtime guarantee**: getAttributes() chứa List<Object>.
3. **Tự điền employeeId/tenant mặc định khi thiếu**: có thể liên kết nhầm tài khoản.
4. **Nhầm FriendlyName và Attribute.Name**: lookup sai khi IdP dùng URN/OID.
5. **Tự split group CSV** khi không có thỏa thuận.
6. **Coi email là identity bất biến** dù IdP có thể đổi/cấp lại.
7. **Bỏ issuer/tenant khỏi account key** khi hỗ trợ nhiều IdP.
8. **Cấp ROLE_ADMIN khi groups thiếu** thay vì deny.
9. **Tự gán authority từ mọi group bên ngoài** thay vì mapping allowlist.
10. **String.valueOf với mọi Object lạ** rồi dùng làm security identifier.
11. **Đọc raw SAMLResponse trước khi framework xác minh**.
12. **Tưởng 403 ở controller đã chặn login**, dù session có thể được tạo.
13. **Tin RequestedAttribute isRequired tự bảo đảm runtime claim presence**.
14. **Trim/case-fold tất cả tên định danh** mà không có quy tắc schema.
15. **Log raw attributes/Response**, làm lộ dữ liệu riêng tư.
16. **Tắt signature validation vì attribute sai/thiếu**, là sửa sai tầng và phá trust.

## 13. Câu hỏi ôn tập

**Câu 1.** getFirstAttribute("groups") và getAttribute("groups") khác nhau thế nào?  
**Đáp án:** getFirstAttribute lấy một giá trị đầu tiên hoặc null, còn getAttribute trả danh sách hoặc null. Dùng danh sách khi muốn nhiều group và kiểm kiểu/cardinality theo contract.

**Câu 2.** employeeId=["EMP-041","EMP-042"] được IdP ký hợp lệ. Có được dùng EMP-041 liên kết tài khoản không?  
**Đáp án:** Không nếu contract yêu cầu đơn trị; phải từ chối **CARDINALITY**.

**Câu 3.** groups không có nhưng SAML login thành công, có thể cấp admin không?  
**Đáp án:** Không. Nhóm thiếu không chứng minh membership; quyền theo deny by default và mapping allowlist.

**Câu 4.** Attribute.Name là urn:oid:0.9.2342.19200300.100.1.3, FriendlyName là email. getAttribute("email") chắc chắn có dữ liệu?  
**Đáp án:** Không; phải tìm đúng Attribute.Name/id do IdP và Spring ánh xạ.

**Câu 5.** Giá trị Number 42 nằm trong employeeId, có thể String.valueOf để tiếp tục không?  
**Đáp án:** Không mặc định. Kiểu dữ liệu không khớp contract cần **TYPE** hoặc converter được phê duyệt riêng.

**Câu 6.** Controller /account trả 403 khi employeeId thiếu. Login SAML đã bị từ chối toàn bộ chưa?  
**Đáp án:** Chưa chắc; Saml2Authentication có thể đã được tạo. Nếu cần chặn login, đặt required claim policy trong post-validation auth conversion/provisioning.

**Câu 7.** Metadata có RequestedAttribute isRequired=true mà IdP không phát attribute. Ứng dụng tự được bảo vệ không?  
**Đáp án:** Không nên giả định; ứng dụng phải kiểm thuộc tính thực nhận và thiết lập chính sách fail closed.

**Câu 8.** Hai IdP phát cùng employeeId có được trộn một local account?  
**Đáp án:** Chỉ khi có chính sách account linking được phê duyệt; mặc định phân tách theo IdP/issuer hoặc stable subject namespace.

## 14. Tài liệu chuẩn

1. [Spring Security 6.5 API – Saml2AuthenticatedPrincipal](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): getAttribute, getFirstAttribute, getAttributes, getRelyingPartyRegistrationId.
2. [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): cách sử dụng Saml2AuthenticatedPrincipal, mapping authorities và customization. Dùng reference đúng phiên bản Spring Security khi triển khai.
3. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): xác minh Response và ánh xạ AttributeStatement thành Map<String,List<Object>>.
4. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AttributeStatement, Attribute, AttributeValue, Name/NameFormat/FriendlyName.
5. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): AttributeConsumingService và RequestedAttribute/isRequired.

**Ghi nhớ:** SAML attributes có thể **đơn trị, đa trị hoặc thiếu**. Sau khi Spring Security xác thực Assertion, ứng dụng phải kiểm **presence, cardinality, kiểu, định dạng và nguồn tin cậy** trước khi dùng chúng làm danh tính/quyền. Với thuộc tính bắt buộc, **fail closed ở đúng tầng**; với thuộc tính tùy chọn, dùng fallback chỉ khi không ảnh hưởng bảo mật.
