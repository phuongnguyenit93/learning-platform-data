# Xây dựng chức năng tìm kiếm danh bạ từ schema đến API

Bài thực hành thuộc chương **Thực hành** của `SPRING_DATA_LDAP`. Bạn sẽ xây dựng một chức năng tìm kiếm danh bạ nhân viên hoàn chỉnh: thiết kế cây LDAP và schema, tạo dữ liệu bằng LDIF, ánh xạ entry sang Java với Spring Data LDAP, truy vấn bằng `LdapTemplate` và công bố REST API để ứng dụng khác gọi.

Ví dụ dùng Java 17+, Spring Boot có Spring Data LDAP, một LDAP directory hỗ trợ schema `inetOrgPerson` và cơ chế TLS. Bạn có thể dùng OpenLDAP hoặc directory thử nghiệm tương đương. Tên miền `example.org`, mật khẩu và tên người đều là dữ liệu minh họa.

## 1. Bài toán, yêu cầu và tiêu chí hoàn thành

Đội nội bộ muốn tra cứu danh bạ theo một phần tên người. Mỗi kết quả gồm mã người dùng, họ tên, email công việc và chức danh. Người gọi API không cần hiểu DN hay LDAP filter.

**Hợp đồng API mục tiêu:**

~~~http
GET /api/v1/contacts?name=An&limit=10
Accept: application/json
~~~

Kết quả minh họa:

~~~json
[
  {
    "uid": "an",
    "fullName": "Nguyen Van An",
    "email": "an@example.org",
    "jobTitle": "Backend Developer"
  }
]
~~~

Yêu cầu thực hành:

1. Mô hình hóa nhân viên bằng `inetOrgPerson`, bảo đảm có `cn` và `sn` theo schema.
2. Chỉ tìm trong nhánh `ou=people,dc=example,dc=org`, không quét toàn directory.
3. Tìm theo chuỗi con của `cn`, bỏ qua những trường hồ sơ không được phép trả ra ngoài.
4. Có kiểm tra dữ liệu đầu vào và giới hạn tối đa 50 kết quả mỗi yêu cầu.
5. Truy vấn LDAP có bộ lọc an toàn; không ghép filter từ đầu vào tự do.
6. Dùng TLS và tài khoản dịch vụ chỉ đọc; thông tin bí mật được cung cấp từ môi trường.
7. Kiểm tra đường đi từ LDIF đến JSON trả về, bao gồm cả ca lỗi.

Kết quả là một đường dẫn dữ liệu rõ ràng:

~~~mermaid
flowchart LR
    A["GET /api/v1/contacts?name=An"] --> B["ContactsController"]
    B --> C["ContactSearchService"]
    C --> D["LdapTemplate + bộ lọc có tham số"]
    D --> E["LDAP directory: ou=people"]
    E --> D
    D --> F["ContactView: dữ liệu công khai được chọn lọc"]
    F --> B
    B --> G["HTTP 200 + JSON"]
~~~

## 2. Thiết kế cây thư mục và schema trước khi viết Java

Thư mục LDAP là cây entry (DIT), không phải bảng quan hệ. Mỗi entry có một **DN** xác định vị trí và các `objectClass` mô tả cấu trúc/thuộc tính.

Cây dữ liệu của bài lab:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   └── uid=mai
└── ou=service
    └── cn=svc-reader
~~~

DN đầy đủ của nhân viên An là:

~~~text
uid=an,ou=people,dc=example,dc=org
~~~

Trong đó `uid=an` là **RDN** của entry, `uid` là một **thuộc tính**, còn toàn bộ chuỗi là **DN**. Đừng đồng nhất ba khái niệm: cùng giá trị `uid` có thể xuất hiện ở những entry khác DN nếu server không cấu hình ràng buộc duy nhất cho thuộc tính.

### Vì sao chọn inetOrgPerson?

`inetOrgPerson` là structural object class kế thừa:

~~~text
top
└── person
    └── organizationalPerson
        └── inetOrgPerson
~~~

Theo schema chuẩn, `person` bắt buộc `cn` và `sn`. `organizationalPerson` bổ sung khả năng lưu thông tin tổ chức; `inetOrgPerson` cho phép các thuộc tính dùng nhiều trong hệ thống nhân sự/danh bạ như `uid`, `mail` và `displayName`. `uid` và `mail` **không trở thành bắt buộc chỉ vì chọn inetOrgPerson**; bài lab yêu cầu `uid` theo quy ước nghiệp vụ riêng.

| Thuộc tính | Vai trò | Ràng buộc áp dụng trong bài lab |
| --- | --- | --- |
| `objectClass` | Cho server biết schema entry. | Có chuỗi `top`, `person`, `organizationalPerson`, `inetOrgPerson`. |
| `uid` | Mã người dùng và RDN của entry. | Bắt buộc theo nghiệp vụ, không trống, duy nhất trong phạm vi quản lý. |
| `cn` | Họ tên dùng để tìm kiếm. | Bắt buộc theo `person`. |
| `sn` | Họ của người dùng. | Bắt buộc theo `person`. |
| `mail` | Email công việc. | Tùy chọn theo schema; API cho phép giá trị `null` khi không có. |
| `title` | Chức danh. | Tùy chọn theo schema; API cho phép giá trị `null` khi không có. |
| `userPassword` | Dữ liệu liên quan xác thực. | Không đưa vào DTO, log hoặc JSON danh bạ. |

**Ranh giới truy cập:** tài khoản `cn=svc-reader,ou=service,dc=example,dc=org` có quyền tìm các thuộc tính cần thiết dưới `ou=people`; nó không cần quyền sửa người dùng hay đọc mật khẩu. Việc cấp quyền cụ thể do ACL của directory quyết định.

## 3. Chuẩn bị dữ liệu mẫu bằng LDIF

Giả định base entry `dc=example,dc=org` và tài khoản dịch vụ đã được quản trị viên tạo trước. Có thể nạp các entry sau vào directory kiểm thử sau khi bảo đảm schema hỗ trợ `inetOrgPerson`.

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=an,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: Nguyen Van An
sn: Nguyen
givenName: An
mail: an@example.org
title: Backend Developer

dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Tran Thi Mai
sn: Tran
givenName: Mai
mail: mai@example.org
title: QA Engineer
~~~

Hãy đặt đoạn trên trong file fixture của **môi trường lab** rồi nhập bằng công cụ LDAP của môi trường, chẳng hạn `ldapadd`. Chỉ dùng tài khoản có quyền thêm entry cho bước thiết lập; ứng dụng chạy API sẽ dùng tài khoản chỉ đọc.

Đọc lại dữ liệu mẫu (lệnh có `-W` để nhập mật khẩu theo lời nhắc, tránh đưa mật khẩu vào lịch sử lệnh):

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-reader,ou=service,dc=example,dc=org" -W \
  -b "ou=people,dc=example,dc=org" \
  "(&(objectClass=inetOrgPerson)(uid=an))" \
  dn objectClass uid cn sn mail title
~~~

Kỳ vọng: có đúng một entry `uid=an`; thấy `cn: Nguyen Van An` và `sn: Nguyen`. Nếu công cụ báo lỗi chứng chỉ TLS hoặc quyền truy cập, cần sửa cấu hình/cấp quyền trước khi tiếp tục.

## 4. Khởi tạo ứng dụng Spring Boot

Với dự án Maven/Gradle đang quản lý phiên bản Spring Boot và dependency tương thích, thêm các starter:

- `spring-boot-starter-data-ldap`: hỗ trợ Spring Data LDAP và Spring LDAP.
- `spring-boot-starter-web`: xây dựng REST API.
- `spring-boot-starter-validation`: phục vụ các ràng buộc đầu vào khi mở rộng API.
- `spring-boot-starter-test`: tạo kiểm thử đơn vị và tích hợp.

Đây là các **tên dependency**, không phải đoạn cấu hình build hoàn chỉnh. Khi dùng Spring Boot, hãy để BOM/plugin của dự án quản lý phiên bản tương thích thay vì tự ghép các phiên bản Spring LDAP khác nhau.

Cấu hình `application.yml`:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Biến môi trường `LDAP_BIND_PASSWORD` cung cấp mật khẩu service account. Cần cấu hình truststore/chứng chỉ để JVM xác minh **chứng chỉ và tên máy chủ LDAP**. Dùng `ldaps://` hoặc StartTLS đã thiết lập thành công **trước khi Bind**; không tắt xác minh TLS chỉ để làm cho lab chạy.

Tùy môi trường, bạn có thể dùng các package:

~~~text
com.example.directory
├── DirectoryApplication.java
├── model/DirectoryPerson.java
├── repository/DirectoryPersonRepository.java
├── api/ContactView.java
├── service/ContactSearchService.java
├── web/ContactsController.java
└── web/DirectoryErrorHandler.java
~~~

Các đoạn Java dưới đây là các file minh họa độc lập, cùng nằm trong một project Spring Boot. Thêm package/import như ví dụ và bật component scanning theo package gốc của ứng dụng.

## 5. Ánh xạ LDAP entry thành đối tượng Java

Spring Data LDAP dùng ODM mapping để chuyển entry thành Java object. `@Entry` mô tả base và object class; `@Id` lưu DN (kiểu `javax.naming.Name`); `@Attribute` ánh xạ giá trị LDAP sang trường Java.

`model/DirectoryPerson.java`:

~~~java
package com.example.directory.model;

import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    @Attribute(name = "title")
    private String jobTitle;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) { this.commonName = commonName; }

    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getJobTitle() { return jobTitle; }
    public void setJobTitle(String jobTitle) { this.jobTitle = jobTitle; }
}
~~~

Ở ví dụ này, `@Entry(base = "ou=people")` chỉ nhánh tương đối với base `dc=example,dc=org` cấu hình trong `ContextSource`. Trường `dn` không phải mã tự tăng kiểu cơ sở dữ liệu quan hệ; đó là địa chỉ entry trong cây LDAP.

Ánh xạ `cn` và `mail` sang một `String` có nghĩa ứng dụng đang **giả định mỗi trường chỉ sử dụng một giá trị**. Một số thuộc tính LDAP cho phép nhiều giá trị; nếu dữ liệu của tổ chức dùng chúng, cần thiết kế collection và kiểm tra mapping thích hợp.

Repository cung cấp cách truy vấn theo thuộc tính đã ánh xạ, thuận tiện cho thao tác chính xác theo `uid`:

`repository/DirectoryPersonRepository.java`:

~~~java
package com.example.directory.repository;

import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;
import com.example.directory.model.DirectoryPerson;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    Optional<DirectoryPerson> findByUid(String uid);
}
~~~

`findByUid` giúp thực hiện một phép tìm theo thuộc tính `uid`. Phần chức năng tìm theo **chuỗi con của tên** ở các bước tiếp theo sẽ dùng `LdapTemplate` để kiểm soát base, phạm vi tìm kiếm, bộ lọc và giới hạn số kết quả.

**Lưu ý tính duy nhất:** `Optional<DirectoryPerson>` chỉ thích hợp khi ứng dụng/directory bảo đảm duy nhất `uid` trong phạm vi tìm kiếm; schema của `inetOrgPerson` không tự ràng buộc mọi `uid` là duy nhất.

## 6. Chọn DTO cho dữ liệu trả về API

API không nên xuất trực tiếp đối tượng `DirectoryPerson`, vì sau này entity có thể chứa DN, thuộc tính nội bộ hoặc thông tin không nên công bố.

`api/ContactView.java`:

~~~java
package com.example.directory.api;

public record ContactView(
    String uid,
    String fullName,
    String email,
    String jobTitle
) {}
~~~

DTO là hợp đồng giữa ứng dụng và client. Bốn trường được chọn đủ cho chức năng danh bạ; không có DN, ACL, `objectClass` hoặc thuộc tính liên quan mật khẩu. Phân quyền xem danh bạ vẫn phải được thực hiện ở tầng API và LDAP.

## 7. Viết lớp tìm kiếm bằng LdapTemplate

Ví dụ hỗ trợ tìm một phần tên với các quy tắc:

- `name` dài 2–60 ký tự, chỉ gồm chữ Unicode, dấu tiếng Việt, số, khoảng trắng và một vài dấu thường có trong tên.
- Từ khóa chứa `*`, `(`, `)`, dấu gạch chéo ngược hoặc ký tự điều khiển sẽ bị từ chối; đây là quy tắc **đầu vào của bài lab**, có thể điều chỉnh theo tên thật của người dùng.
- `limit` nằm trong khoảng 1–50.
- Chỉ tìm **entry con trực tiếp** của `ou=people`, có `objectClass=inetOrgPerson`, `cn` chứa từ khóa.
- Bộ lọc được tạo bằng API của Spring LDAP, không nối nguyên filter từ request.

`service/ContactSearchService.java`:

~~~java
package com.example.directory.service;

import java.util.List;
import java.util.regex.Pattern;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import com.example.directory.api.ContactView;

@Service
public class ContactSearchService {

    private static final Pattern SAFE_NAME =
            Pattern.compile("[\\p{L}\\p{M}0-9 .'-]{2,60}");

    private final LdapTemplate ldapTemplate;

    public ContactSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<ContactView> searchByName(String name, int limit) {
        String term = name == null ? "" : name.strip();

        if (!SAFE_NAME.matcher(term).matches()) {
            throw new IllegalArgumentException(
                    "name must contain 2..60 valid characters");
        }
        if (limit < 1 || limit > 50) {
            throw new IllegalArgumentException(
                    "limit must be between 1 and 50");
        }

        // Chỉ dấu * do ứng dụng thêm vào để tìm substring.
        // term không chứa toán tử/filter control từ người dùng.
        String pattern = "*" + term + "*";

        LdapQuery query = LdapQueryBuilder.query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .countLimit(limit)
                .timeLimit(3_000)
                .where("objectClass").is("inetOrgPerson")
                .and("cn").like(pattern);

        return ldapTemplate.search(
                query,
                (ContextMapper<ContactView>) context -> {
                    DirContextOperations entry =
                            (DirContextOperations) context;
                    return new ContactView(
                            entry.getStringAttribute("uid"),
                            entry.getStringAttribute("cn"),
                            entry.getStringAttribute("mail"),
                            entry.getStringAttribute("title")
                    );
                });
    }
}
~~~

### Vì sao truy vấn này an toàn hơn ghép filter?

Đoạn code kiểm tra từ khóa **trước khi** xây dựng bộ lọc, loại những ký tự LDAP filter đặc biệt khỏi phần dữ liệu người dùng có thể kiểm soát. `LdapQueryBuilder` áp dụng các thao tác truy vấn có cấu trúc; dấu `*` được **ứng dụng tự đưa vào** để biểu thị tìm chuỗi con. Do đó không có đường cho người dùng chèn tùy ý một biểu thức filter hoàn chỉnh như `(|(cn=*)(uid=*))`.

Trong ứng dụng thực tế, đôi khi tên hợp lệ có dấu ngoặc, dấu sao hoặc các ký tự khác. Khi đó cần thiết kế cơ chế **escape giá trị dữ liệu** theo RFC 4515, đồng thời cho phép wildcard do ứng dụng xác định; không nên chỉ mở rộng regex rồi nối giá trị chưa escape vào filter.

Các cấu hình tìm kiếm có ý nghĩa:

| Thiết lập | Tác dụng |
| --- | --- |
| `.base("ou=people")` | Giới hạn nhánh tìm kiếm, tương đối với base của connection. |
| `SearchScope.ONELEVEL` | Chỉ tìm entry con trực tiếp của `ou=people`; chuyển sang `SUBTREE` nếu người dùng được đặt ở nhiều nhánh con. |
| `objectClass=inetOrgPerson` | Chỉ nhận entry thuộc lớp người dùng mong muốn. |
| `cn` với `like("*An*")` | Tìm tên chứa `An` theo matching rule của directory. |
| `countLimit(limit)` | Yêu cầu giới hạn số entry trả về trong phép tìm. |
| `timeLimit(3_000)` | Giới hạn thời gian tìm ở phía truy vấn; vẫn cần cấu hình timeout kết nối/đọc phù hợp. |

LDAP server có thể có các giới hạn riêng về kết quả, thời gian và ACL. Kết quả theo `countLimit` **không tương đương phân trang ổn định**; nếu cần duyệt thư mục lớn, phải thiết kế giải pháp phân trang phù hợp với LDAP server (ví dụ simple paged results control) và thứ tự/độ ổn định kết quả.

Đặc biệt, thao tác **substring search với dấu `*` đầu chuỗi** có thể tốn tài nguyên khi dữ liệu lớn. Khi triển khai thật, cần xem xét chỉ mục LDAP, độ dài từ khóa tối thiểu, giới hạn tốc độ API và khả năng tìm tiền tố thay vì chuỗi con.

## 8. Tạo REST controller và xử lý lỗi có chủ đích

`web/ContactsController.java`:

~~~java
package com.example.directory.web;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.example.directory.api.ContactView;
import com.example.directory.service.ContactSearchService;

@RestController
@RequestMapping("/api/v1/contacts")
public class ContactsController {

    private final ContactSearchService searchService;

    public ContactsController(ContactSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping
    public List<ContactView> search(
            @RequestParam("name") String name,
            @RequestParam(name = "limit", defaultValue = "20") int limit) {

        return searchService.searchByName(name, limit);
    }
}
~~~

Spring MVC chuyển `List<ContactView>` thành JSON. Khi `name` thiếu, framework thường trả `400 Bad Request` do thiếu tham số bắt buộc. Khi `limit` không thể chuyển thành số nguyên, framework cũng xử lý thành lỗi đầu vào.

Với lỗi do service tự phát hiện, nên trả mã rõ ràng thay vì để thông báo nội bộ lọt tới client. `web/DirectoryErrorHandler.java`:

~~~java
package com.example.directory.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.ldap.NamingException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DirectoryErrorHandler {

    public record ApiError(String code, String message) {}

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> badQuery() {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_QUERY",
                        "Invalid directory search parameters"));
    }

    @ExceptionHandler(NamingException.class)
    public ResponseEntity<ApiError> ldapUnavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError(
                        "DIRECTORY_UNAVAILABLE",
                        "Directory service is temporarily unavailable"));
    }
}
~~~

Đây là **quy ước lỗi đơn giản cho lab**: hệ thống sản xuất cần phân biệt chi tiết lỗi quyền truy cập, timeout, quá giới hạn, truy vấn sai, lỗi cấu hình và lỗi hạ tầng trong log nội bộ; không lộ địa chỉ directory, DN, mật khẩu hay chi tiết stack trace cho người dùng API.

### Các HTTP response kỳ vọng

| Yêu cầu | HTTP dự kiến | Phản hồi |
| --- | --- | --- |
| `GET /api/v1/contacts?name=An&limit=10` | 200 | JSON array các nhân viên phù hợp, tối đa 10 phần tử. |
| `GET /api/v1/contacts?name=ZZZZ` | 200 | `[]` nếu không khớp. |
| `GET /api/v1/contacts?name=A` | 400 | Từ khóa ngắn hơn yêu cầu 2 ký tự. |
| `GET /api/v1/contacts?name=An&limit=1000` | 400 | `limit` vượt quá 50. |
| `GET /api/v1/contacts?name=*` | 400 | Không chấp nhận ký tự wildcard từ client. |
| `GET /api/v1/contacts` | 400 | Thiếu tham số `name`. |
| Directory không truy cập được và phát sinh `NamingException` | 503 | Thông báo lỗi chung, không lộ thông tin kết nối. |

Nếu API công khai trong nội bộ doanh nghiệp, nên đặt cơ chế xác thực và phân quyền HTTP ở phía trước controller, ví dụ Spring Security cho nhóm có quyền xem danh bạ, kết hợp giới hạn tần suất và audit phù hợp. **Bind bằng tài khoản dịch vụ LDAP không tự xác thực người gọi HTTP.**

## 9. Chạy thử từ directory đến API

Trước hết xác minh directory có dữ liệu bằng `ldapsearch`. Sau đó chạy ứng dụng với biến môi trường cung cấp mật khẩu (không nhập mật khẩu vào command trực tiếp nếu môi trường ghi lịch sử command).

Khi Spring Boot đã khởi động trên máy phát triển và endpoint ở `localhost:8080`, gửi:

~~~bash
curl --get "http://localhost:8080/api/v1/contacts" \
  --data-urlencode "name=An" \
  --data-urlencode "limit=10"
~~~

Kết quả dự kiến khi dữ liệu LDIF đã nạp:

~~~json
[
  {
    "uid": "an",
    "fullName": "Nguyen Van An",
    "email": "an@example.org",
    "jobTitle": "Backend Developer"
  }
]
~~~

Chạy thêm một truy vấn không có kết quả:

~~~bash
curl --get "http://localhost:8080/api/v1/contacts" \
  --data-urlencode "name=KhongTonTai"
~~~

Kỳ vọng `[]`. Thử `name=*` hoặc `limit=1000` để thấy lỗi `400`. Nếu môi trường đã bật Spring Security, các ví dụ `curl` cần bổ sung cơ chế xác thực HTTP tương ứng.

**Lưu ý:** URL HTTP chỉ nhằm kiểm thử ứng dụng ở `localhost`. Khi triển khai cho người dùng thật, API nên được xuất qua HTTPS và có chính sách xác thực/phân quyền; kết nối **từ API đến LDAP** vẫn phải được mã hóa riêng.

## 10. Ma trận kiểm thử và tiêu chí nghiệm thu

Nên có một LDAP directory dành riêng cho kiểm thử tích hợp với fixture xác định, để các phép thử không phụ thuộc dữ liệu nhân sự thật.

| Trường hợp | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Schema hợp lệ | Nạp LDIF với `cn`, `sn` và chuỗi object class. | Directory chấp nhận cả hai entry mẫu. |
| Schema thiếu dữ liệu | Thử tạo `inetOrgPerson` không có `sn`. | Directory kiểm tra schema từ chối entry. |
| Đúng nội dung tìm kiếm | `name=An` | Trả về nhân viên An từ `ou=people`. |
| Không tìm thấy | `name=KhongTonTai` | HTTP 200, JSON `[]`. |
| Dữ liệu tùy chọn trống | Bỏ `title` khỏi fixture. | Kết quả vẫn có người dùng, `jobTitle` là `null` (nếu không cấu hình serializer bỏ null). |
| Kiểm soát nhánh | Thêm entry khớp tên ngoài `ou=people`. | Entry ngoài nhánh không xuất hiện. |
| Giới hạn số kết quả | Nạp hơn 50 entry khớp rồi gửi `limit=50`. | Không trả quá 50 entry; tùy server có thể áp dụng giới hạn/chính sách khác. |
| Đầu vào không an toàn | `name=*`, `name=(cn=*)`, `name=An) (|...` | Bị từ chối `400`; không biến thành filter khác. |
| Từ khóa quá ngắn | `name=A` | HTTP 400. |
| Directory bị ngắt kết nối | Tắt thử directory hoặc chặn kết nối test. | API phản hồi lỗi có kiểm soát; không hiển thị thông tin nhạy cảm. |
| Service account không có quyền đọc `mail` | Áp ACL cho tài khoản test. | Thực tế thuộc tính bị ẩn hoặc truy vấn bị từ chối tùy ACL; không được tự nâng quyền. |
| Kiểm tra TLS | Dùng chứng chỉ không tin cậy trong môi trường test. | Kết nối bị từ chối; ứng dụng không tự hạ cấp về plaintext. |
| Thay đổi dữ liệu | Sửa `title` của An, truy vấn lại. | Nhận giá trị mới theo directory, trừ khi ứng dụng chủ động bật cache. |

Kiểm thử đơn vị có thể mock lớp truy vấn để xác minh đầu vào hợp lệ/không hợp lệ và ánh xạ DTO. Kiểm thử tích hợp phải thực sự trao đổi với directory có schema, bởi mock không thể thay thế việc phát hiện `objectClassViolation`, ACL, giới hạn tìm kiếm hay khác biệt matching rule giữa server.

Để kiểm tra hoạt động của repository, có thể dùng một kiểm thử tích hợp gọi `findByUid("an")` và xác minh `getCommonName()` bằng `Nguyen Van An`. Nếu truy vấn repository thất bại trong khi `ldapsearch` thành công, hãy kiểm tra base DN, scope, annotation mapping và quyền của service account.

## 11. Phân tích và xử lý các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `objectClassViolation` khi thêm entry | Thiếu `cn`/`sn` hoặc thuộc tính không được object class cho phép. | Kiểm tra LDIF và schema `inetOrgPerson` trên server. |
| `No Such Object` | `ou=people` chưa được tạo hoặc base DN sai. | Kiểm tra DIT và cặp `spring.ldap.base` / `@Entry(base)` / `LdapQuery.base`. |
| `Invalid credentials` khi khởi động hoặc truy vấn | DN hoặc mật khẩu service account sai, hoặc bị chính sách xác thực từ chối. | Kiểm tra tài khoản và TLS; không in mật khẩu ra log. |
| Tìm thấy với `ldapsearch` nhưng API ra `[]` | Sai scope, base, filter, case/matching rule hoặc quyền đọc. | So sánh filter, DN gốc, `ONELEVEL` và ACL; thử lại cùng danh tính Bind. |
| Kết quả trả về lẫn dữ liệu ngoài nhánh | Base/scope quá rộng. | Giới hạn `ou=people` và kiểm tra môi trường cấu hình. |
| Giá trị email hoặc chức danh rỗng | Thuộc tính không có, khác tên, đa giá trị hoặc bị ACL ẩn. | Đọc lại entry bằng chính service account. |
| Timeout hoặc truy vấn chậm | Search substring tốn tài nguyên, thiếu index hoặc directory quá lớn. | Đánh giá index, search scope, thời gian chờ, rate limit, phân trang. |
| Thông tin nhạy cảm lộ qua API | Trả thẳng entity hoặc serialize toàn bộ Attributes. | Dùng DTO chứa danh sách trường công khai cố định. |

## 12. Mở rộng bài thực hành sau khi đã chạy ổn định

Sau khi endpoint cơ bản hoạt động, có thể mở rộng theo các hướng thực tế:

1. **Tìm theo nhiều điều kiện:** hỗ trợ phòng ban `ou` hoặc mã `uid`; xác định rõ khi nào dùng AND/OR, validate từng tham số và giữ ranh giới truy cập.
2. **Phân trang LDAP thật:** sử dụng cơ chế paged results của directory và xử lý cookie giữa các trang. Không giả lập phân trang LDAP bằng cách lấy toàn bộ rồi `skip/limit` trong Java.
3. **Sắp xếp và hiệu năng:** nghiên cứu server-side sort nếu server hỗ trợ; kiểm thử chỉ mục đối với truy vấn tên và quy mô dữ liệu thật.
4. **Phân quyền API:** chỉ người dùng hoặc nhóm đã đăng nhập mới được tra cứu; service account LDAP chỉ cấp quyền đọc tối thiểu.
5. **Xử lý thay đổi DN:** nếu mở rộng API để tạo/cập nhật hồ sơ, dùng API DN/ODM thích hợp và thao tác Modify DN cho việc đổi RDN. Không ghép DN từ đầu vào người dùng hay cho phép API tìm kiếm tự tiện sửa dữ liệu.
6. **Theo dõi vận hành:** đo độ trễ, tỷ lệ lỗi TLS/LDAP, số lượng kết quả và rate limit nhưng không log mật khẩu, giá trị lọc chứa dữ liệu nhạy cảm hoặc hồ sơ đầy đủ khi không cần thiết.

## 13. Câu hỏi tự đánh giá

1. Vì sao entry `inetOrgPerson` vẫn bắt buộc `cn` và `sn`?
2. Nếu một nhân viên có `uid=an` thì DN của họ được tạo từ những thành phần nào? Vì sao `uid` không tự động duy nhất trong toàn directory?
3. Tại sao API nên trả `ContactView` thay vì serialize `DirectoryPerson`?
4. `SearchScope.ONELEVEL` và `SearchScope.SUBTREE` khác nhau thế nào khi đặt nhân viên trong các OU con?
5. Vì sao bộ lọc tìm chuỗi con sử dụng ký tự `*` cần phân biệt wildcard do ứng dụng định nghĩa với ký tự do người dùng nhập?
6. Vì sao `countLimit(50)` chưa đủ để triển khai phân trang chuẩn cho một danh bạ lớn?
7. Có thể coi tài khoản service LDAP đã Bind là chứng cứ người gọi REST API đã được xác thực không?
8. Nếu `ldapsearch` trả dữ liệu nhưng API lại không tìm thấy, những giả thuyết nào nên kiểm tra đầu tiên?

**Kết quả cần đạt:** Có một directory với schema và LDIF hợp lệ, một đối tượng Java ánh xạ được entry, một truy vấn `LdapTemplate` kiểm soát phạm vi và filter, và một REST API trả đúng danh bạ qua DTO. Khi chuyển từ lab sang môi trường thật, phải giữ các ràng buộc TLS, ACL, bảo mật HTTP, giới hạn tìm kiếm và kiểm thử tích hợp.

### Tài liệu tham khảo

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): mô hình entry, DN, object class và schema.
- [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798): object class `inetOrgPerson`.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp và escaping cho filter LDAP.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): ánh xạ ODM và repository.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `LdapQueryBuilder` và cấu hình LDAP context.
