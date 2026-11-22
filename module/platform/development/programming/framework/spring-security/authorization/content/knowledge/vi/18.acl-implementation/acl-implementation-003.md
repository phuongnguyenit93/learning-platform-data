# `AclAuthorizationStrategy` và `PermissionGrantingStrategy` trong Spring Security ACL

## 1. Hai chiến lược bảo mật giải quyết hai câu hỏi khác nhau

Xét ACL của tài liệu `Document#42`:

- `alice` là **chủ sở hữu ACL** (`Acl.getOwner()`).
- `bob` có ACE `READ GRANT` đối với tài liệu.
- `carol` có ACE `READ DENY`.
- `dave` có ACE `ADMINISTRATION GRANT`.
- `root` có `GrantedAuthority` hệ thống `ROLE_ACL_ADMIN`.

Đừng vội kết luận rằng `alice` đọc được tài liệu hay `bob` được sửa ACL. Hệ thống phải trả lời **hai câu hỏi độc lập**:

1. **Ai được thay đổi chính danh sách quyền?** Ví dụ thêm ACE, xóa ACE, đổi ACL owner hay thay cấu hình audit. Đây là trách nhiệm của `AclAuthorizationStrategy`.
2. **Ai được thực hiện một hành động trên đối tượng được bảo vệ?** Ví dụ `READ`, `WRITE` hoặc `DELETE` trên tài liệu. Đây là trách nhiệm của `PermissionGrantingStrategy`.

Trong Spring Security ACL, `AclImpl` có cả hai chiến lược. Khi gọi mutator của ACL, nó kiểm soát thay đổi thông qua chiến lược quản trị; khi hỏi `Acl.isGranted(...)`, nó chuyển việc xét ACE/SID/permission cho chiến lược cấp quyền.

Những điểm cần nhớ ngay từ đầu:

- **ACL owner không mặc định là domain object reader.**
- **ACE `READ` không mặc định cấp quyền chỉnh ACL.**
- `BasePermission.ADMINISTRATION` có thể góp phần cho phép quản trị ACL, nhưng **không phải** `READ | WRITE | DELETE`.
- User được quyền thay ACL có thể **gián tiếp tự thêm quyền dữ liệu** nếu nghiệp vụ cho phép grant tùy ý. Vì vậy cần cả policy quản trị ở service.
- Thứ tự permissions, thứ tự SIDs, bitmask, deny, parent ACL và audit mode có thể ảnh hưởng đến kết quả. Không tự viết tắt thuật toán bằng `anyMatch`.

Bài này thuộc chủ đề **Triển khai ACL** của Spring Security authorization. Sau bài, bạn có thể giải thích contract, cấu hình hai strategy, chạy ví dụ Java 17+ với **chính các class ACL của Spring Security**, viết test, và áp dụng cơ chế fail closed trong sản phẩm.

## 2. Các thành phần chung của Spring ACL

Một ACL gắn với một `ObjectIdentity` (loại đối tượng + ID) và chứa các `AccessControlEntry` (ACE). Mỗi ACE nối một `Sid` với một `Permission` và cờ cho phép/từ chối.

```text
ObjectIdentity = demo.Document#42
      |
      v
   AclImpl
     ownerSid = PrincipalSid("alice")
     entriesInheriting = false
     parentAcl = null
      |
      +-- ACE 0: bob   READ             GRANT
      +-- ACE 1: carol READ             DENY
      +-- ACE 2: dave  ADMINISTRATION   GRANT
      +-- ACE 3: erin  WRITE            GRANT
      |
      +-- AclAuthorizationStrategy
      |     Khi muốn chỉnh owner/ACE/audit
      |
      +-- PermissionGrantingStrategy
            Khi kiểm tra READ/WRITE/... theo SID
```

| Thành phần | API | Nhiệm vụ |
| --- | --- | --- |
| Định danh đối tượng | `ObjectIdentity`, `ObjectIdentityImpl` | Xác định ACL cho một object |
| Định danh bảo mật | `Sid`, `PrincipalSid`, `GrantedAuthoritySid` | Đại diện user hoặc authority |
| Quyền | `Permission`, `BasePermission` | Biểu diễn quyền dưới dạng bitmask |
| Dòng quyền | `AccessControlEntry` | ACE grant/deny cho SID + permission |
| Danh sách kiểm soát | `Acl`, `MutableAcl`, `AclImpl` | Owner, parent, entries, mutators và kiểm tra quyền |
| Quản trị ACL | `AclAuthorizationStrategy` | Caller được thay ACL không? |
| Permission trên object | `PermissionGrantingStrategy` | SID được cấp quyền cụ thể không? |
| Kho ACL | `AclService`, `MutableAclService` | Đọc, tạo và cập nhật ACL |
| Method Security | `AclPermissionEvaluator` | Phục vụ `hasPermission(...)` trong biểu thức |
| Bộ nạp JDBC | `BasicLookupStrategy` | Nạp ACE/owner/SID và dựng ACL |
| Bộ nhớ đệm | `AclCache`, `SpringCacheBasedAclCache` | Cache ACL đã được nạp |

**Domain owner** (`document.ownerUserId`) là thuộc tính nghiệp vụ, khác `Acl.getOwner()` là metadata ACL. Việc thay một owner không tự thay owner còn lại hoặc tự thêm ACE READ.

### Các bit permission chuẩn

| Hằng `BasePermission` | Mask |
| --- | ---: |
| `READ` | 1 |
| `WRITE` | 2 |
| `CREATE` | 4 |
| `DELETE` | 8 |
| `ADMINISTRATION` | 16 |

Đây là các bit riêng. Không suy luận `WRITE` bao gồm `READ` hay `ADMINISTRATION` tự động bao gồm cả bốn bit trước. Nếu doanh nghiệp cần phân cấp quyền, nó phải được định nghĩa, cấu hình và kiểm thử rõ ràng.

## 3. `AclAuthorizationStrategy`: quyết định ai được sửa ACL

Interface thật thuộc package:

```java
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
```

Contract có phương thức:

```java
void securityCheck(Acl acl, int changeType);
```

Đây là chữ ký rút gọn, không phải một file Java tự chạy. Nó **không trả boolean**: lời gọi kết thúc bình thường khi được phép, hoặc ném exception nếu không được phép. API được dùng ở những thao tác thay đổi ACL của `AclImpl`.

### 3.1. Ba loại thay đổi

Interface khai báo ba hằng:

| Hằng | Nhóm thay đổi | Ví dụ |
| --- | --- | --- |
| `CHANGE_GENERAL` | Thay thông tin ACL hoặc ACE thông thường | `insertAce`, `deleteAce`, `updateAce`, parent ACL |
| `CHANGE_OWNERSHIP` | Thay owner SID của ACL | `setOwner(...)` |
| `CHANGE_AUDITING` | Thay cờ audit trên ACE | `updateAuditing(...)` |

Các hằng **không phải** domain permissions. `CHANGE_GENERAL` không đồng nghĩa `BasePermission.WRITE`; `CHANGE_OWNERSHIP` không phải `BasePermission.ADMINISTRATION`.

### 3.2. Chiến lược mặc định cấp quyền theo những căn cứ nào?

`AclAuthorizationStrategyImpl` là implementation phổ biến. Theo Javadoc của Spring Security 6.5, ít nhất một trong các điều kiện sau có thể cho phép một thay đổi ACL:

1. Caller **là ACL owner** theo `Acl.getOwner()`.
2. Caller có **system-wide `GrantedAuthority`** tương ứng loại thay đổi, được inject vào constructor.
3. Caller có quyền **`BasePermission.ADMINISTRATION`** theo ACL và permission strategy.

Vì đây là quyền **đổi danh sách quyền**, không thể suy ra owner ACL tự được phép đọc nội dung của domain object.

Cấu hình một authority cho mọi nhóm thay đổi:

```java
@Bean
AclAuthorizationStrategy aclAuthorizationStrategy() {
    return new AclAuthorizationStrategyImpl(
        new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
    );
}
```

Đây là **mảnh cấu hình Spring**. Những lớp trên nằm ở `org.springframework.security.acls.domain`, còn `SimpleGrantedAuthority` ở `org.springframework.security.core.authority`. Role trong ví dụ do ứng dụng định nghĩa, không phải role bắt buộc do Spring ACL tạo.

### 3.3. Truyền ba authority riêng

Constructor `AclAuthorizationStrategyImpl(GrantedAuthority... auths)` cho phép một authority dùng chung hoặc ba authority riêng. Khi có ba, thứ tự tham số **cần giữ chính xác**:

```java
new AclAuthorizationStrategyImpl(
    new SimpleGrantedAuthority("ROLE_ACL_OWNER_ADMIN"),
    new SimpleGrantedAuthority("ROLE_ACL_AUDIT_ADMIN"),
    new SimpleGrantedAuthority("ROLE_ACL_ENTRY_ADMIN")
);
```

| Vị trí | Loại thay đổi |
| --- | --- |
| Index 0 | `CHANGE_OWNERSHIP` |
| Index 1 | `CHANGE_AUDITING` |
| Index 2 | `CHANGE_GENERAL` |

Đây là **phương án thay thế** cấu hình một authority. Nếu dùng ba authority, đừng nghĩ rằng việc phân nhóm tự loại bỏ quyền của ACL owner hoặc ACE `ADMINISTRATION`: implementation mặc định có các căn cứ cho phép khác. Nếu chính sách yêu cầu **chỉ** người compliance mới được đổi owner và ACL owner không được đổi, cần chính sách ở service hoặc custom strategy, không chỉ thay tên role.

### 3.4. Identity trong chiến lược quản trị

Chiến lược mặc định lấy authentication theo `SecurityContextHolderStrategy`/`SecurityContextHolder`. Trong HTTP request, authentication phải được tạo bởi filter/provider đáng tin; trong job có thể là service identity được thiết lập theo quy trình riêng. Không lấy username client gửi rồi tự tạo token đã xác thực để tự cấp quyền ACL.

`AclAuthorizationStrategyImpl` còn hỗ trợ các tùy chọn như `SidRetrievalStrategy`, `RoleHierarchy` và security-context strategy. Khi tổ chức có username trùng nhau qua tenant hoặc hierarchy role phức tạp, cần kiểm chứng SID mapping; không tự dùng email/username tự khai làm định danh global.

## 4. `PermissionGrantingStrategy`: quyết định quyền trên domain object

Interface nằm trong **package khác**:

```java
import org.springframework.security.acls.model.PermissionGrantingStrategy;
```

Chữ ký cốt lõi:

```java
boolean isGranted(
    Acl acl,
    List<Permission> permissions,
    List<Sid> sids,
    boolean administrativeMode
);
```

Điều cần phân biệt:

- `permissions`: danh sách những quyền cần thử, như `READ`, `WRITE`.
- `sids`: các principal/role được xét.
- `administrativeMode`: cờ chế độ audit, **không phải** permission `ADMINISTRATION`.
- Giá trị trả về có thể là `true` hoặc `false`.
- Khi không thể đưa ra quyết định, `DefaultPermissionGrantingStrategy` có thể ném `NotFoundException`; khi ACL chưa nạp SID cần thiết, có thể có `UnloadedSidException`.

Implementation phổ biến:

```java
@Bean
PermissionGrantingStrategy permissionGrantingStrategy() {
    return new DefaultPermissionGrantingStrategy(
        new ConsoleAuditLogger()
    );
}
```

`ConsoleAuditLogger` chỉ là audit logger cơ bản; production có thể cần audit tích hợp với hệ thống logging, retention và giám sát bảo mật.

### 4.1. `AclImpl.isGranted(...)` là điểm gọi chính

```java
boolean allowed = acl.isGranted(
    List.of(BasePermission.READ),
    List.of(new PrincipalSid("bob")),
    false
);
```

Đoạn trên là mảnh code, giả định `acl` đã được nạp. Khi gọi `isGranted`, `AclImpl` ủy quyền cho `PermissionGrantingStrategy` được cấu hình. **Không nên** dùng `acl.getEntries().stream().anyMatch(...)` để thay thế: thứ tự permission/SID, ACE grant/deny, parent ACL, mask và thiếu SID làm kết quả phức tạp hơn.

### 4.2. Thứ tự permissions và SIDs thực sự có ý nghĩa

Với `DefaultPermissionGrantingStrategy`, thuật toán xét từng permission **theo thứ tự danh sách**, và từng SID theo thứ tự trong danh sách. Với mỗi cặp được xét, nó tìm ACE phù hợp theo quy tắc strategy. Grant có thể dẫn đến cho phép; deny có thể khiến strategy thử permission kế tiếp trước khi từ chối cuối cùng.

Điều này có nghĩa:

- Danh sách `[READ, WRITE]` nói rằng **một quyền phù hợp có thể đủ**, không phải bắt buộc AND cả hai.
- Nếu nghiệp vụ cần READ **và** WRITE, kiểm tra từng quyền theo cách độc lập và tổng hợp AND.
- Đổi thứ tự permission/SID hoặc ACE có thể thay đổi quyết định trong các cấu hình có grant/deny.
- Không có quyết định ở ACL hiện tại: có thể xem ACL cha **nếu** `entriesInheriting=true`.
- Vẫn không có quyết định: `NotFoundException`.

**Ví dụ:** `READ DENY`, `WRITE GRANT` không mặc nhiên làm `isGranted([READ, WRITE], ...)` trả `false`; còn tùy thứ tự và cơ chế xét quyền. Vì vậy đừng truyền nhiều quyền rồi gọi đó là yêu cầu đồng thời.

### 4.3. Chi tiết mask của implementation mặc định

Javadoc nêu rằng phép so mask cho một ACE và permission được yêu cầu **không luôn đơn giản là so bằng tuyệt đối**:

- Khi ACE là **GRANT** và requested mask khác 0, bitwise giao nhau có thể được coi là match.
- Trong nhánh **DENY**, implementation mặc định so mask bằng nhau.
- Một ACE mask kết hợp có thể mang nghĩa khác nhiều ACE riêng khi xét một bit.

Đây là hành vi của `DefaultPermissionGrantingStrategy`, không phải lời hứa về mọi custom `PermissionGrantingStrategy`. Nếu dùng permission mask kết hợp, cần unit test đủ grant, deny, nhiều SID và ACL kế thừa.

### 4.4. `administrativeMode` khác `BasePermission.ADMINISTRATION`

So sánh hai lời gọi:

```java
acl.isGranted(
    List.of(BasePermission.READ),
    List.of(new PrincipalSid("bob")),
    false
);
```

```java
acl.isGranted(
    List.of(BasePermission.ADMINISTRATION),
    List.of(new PrincipalSid("dave")),
    true
);
```

Lời gọi đầu kiểm tra **READ**. Lời gọi sau kiểm tra **ADMINISTRATION** vì nó được đặt trong danh sách permission. Boolean `true` trong ví dụ sau chỉ là chế độ **không thực hiện audit** khi đánh giá theo hoạt động hành chính; nó không cấp thêm quyền.

## 5. Hai strategy phối hợp trong vòng đời một ACL

```text
Caller
  |
  +-- Muốn sửa ACL ---------------------+
  |                                     |
  |                                  AclImpl mutator
  |                                  insertAce/setOwner/update...
  |                                     |
  |                                  AclAuthorizationStrategy
  |                                  securityCheck(acl, changeType)
  |                                     |
  |                                 allow / deny
  |
  +-- Muốn READ tài liệu --------------+
                                        |
                                     Method Security
                                     hasPermission(...)
                                        |
                                     AclPermissionEvaluator
                                        |
                                     AclService / Acl
                                        |
                                     AclImpl.isGranted(...)
                                        |
                                     PermissionGrantingStrategy
                                        |
                                     grant / deny / exception
```

| Câu hỏi | Chiến lược | Dữ liệu |
| --- | --- | --- |
| Alice có đổi ACL owner được không? | `AclAuthorizationStrategy` | Current authentication, ACL owner, authorities, admin ACE |
| Bob có `READ` được Document#42 không? | `PermissionGrantingStrategy` | ACL entries, requested permission và SID |
| Một role có `READ` theo ACL cha không? | `PermissionGrantingStrategy` | ACE parent, `entriesInheriting`, SID |
| Editor có thêm ACE cho đồng nghiệp cùng tenant không? | `AclAuthorizationStrategy` **và policy service** | Quyền quản trị ACL + tenant/recipient |
| Có thể đọc nội dung sau khi gọi `setOwner` không? | `PermissionGrantingStrategy` | ACE READ thực tế, không suy từ owner |

**Một cảnh báo:** quyền chỉnh ACL có thể gián tiếp tạo quyền xem dữ liệu (ví dụ tự thêm ACE `READ`). Vì thế việc hai strategy độc lập **không có nghĩa** cho phép bất kỳ ACL owner nào grant mọi quyền tùy ý. Policy service phải giới hạn grant/recipient và có audit.

## 6. Ví dụ Java 17 với chính `AclImpl` của Spring Security

Ta tạo ACL trong bộ nhớ bằng `AclImpl` thật để thực nghiệm hai chiến lược, **không tự mô phỏng thuật toán với Map**. Chương trình không cần Spring Boot server hay database; Gradle quản lý `spring-security-acl` và Spring Security core.

Kịch bản:

- ACL owner = `alice`, nhưng không có ACE READ cho `alice`.
- `bob` có READ GRANT, không có quyền đổi ACL.
- `carol` có READ DENY.
- `dave` có ADMINISTRATION GRANT, không có READ.
- `root` có authority hệ thống `ROLE_ACL_ADMIN`, nhưng cũng không có READ.

### 6.1. Cấu trúc dự án

```text
acl-strategies-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/AclStrategiesDemo.java
    └── test/java/demo/AclStrategiesDemoTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'acl-strategies-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'application'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.8'
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-acl'
    implementation 'org.springframework.security:spring-security-core'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.AclStrategiesDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Gradle Boot BOM dùng để lấy những phiên bản dependency tương thích. Đây là ứng dụng Gradle **`application`**, không có `@SpringBootApplication`, HTTP server hoặc database. Cấu hình này tập trung kiểm chứng chiến lược ACL.

### 6.2. Mã nguồn chương trình

**`src/main/java/demo/AclStrategiesDemo.java`:**

```java
package demo;

import java.util.Arrays;
import java.util.List;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.acls.model.UnloadedSidException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class AclStrategiesDemo {

    private static final AclAuthorizationStrategyImpl CHANGE_STRATEGY =
        new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
        );

    private static final DefaultPermissionGrantingStrategy GRANT_STRATEGY =
        new DefaultPermissionGrantingStrategy(new ConsoleAuditLogger());

    private AclStrategiesDemo() {
    }

    static void login(String name, String... authorities) {
        var grants = Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toList();

        Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                name, "demo-only", grants
            );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    static AclImpl buildSample() {
        AclImpl acl = new AclImpl(
            new ObjectIdentityImpl("demo.Document", 42L),
            1L,
            CHANGE_STRATEGY,
            GRANT_STRATEGY,
            null,  // ACL cha
            null,  // Không giới hạn subset SIDs được nạp
            false, // Không kế thừa ACE
            new PrincipalSid("alice")
        );

        // Chỉ để seed demo: root được cấp quyền hệ thống.
        login("root", "ROLE_ACL_ADMIN");

        acl.insertAce(
            0, BasePermission.READ, new PrincipalSid("bob"), true);
        acl.insertAce(
            1, BasePermission.READ, new PrincipalSid("carol"), false);
        acl.insertAce(
            2, BasePermission.ADMINISTRATION,
            new PrincipalSid("dave"), true);
        acl.insertAce(
            3, BasePermission.WRITE, new PrincipalSid("erin"), true);

        return acl;
    }

    static boolean readAllowed(Acl acl) {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        try {
            return acl.isGranted(
                List.<Permission>of(BasePermission.READ),
                List.<Sid>of(new PrincipalSid(authentication)),
                false
            );
        } catch (NotFoundException | UnloadedSidException denied) {
            return false;
        }
    }

    static boolean canChangeAcl(Acl acl) {
        try {
            CHANGE_STRATEGY.securityCheck(
                acl, AclAuthorizationStrategy.CHANGE_GENERAL);
            return true;
        } catch (AccessDeniedException | NotFoundException denied) {
            return false;
        }
    }

    public static void main(String[] args) {
        try {
            AclImpl acl = buildSample();

            login("alice");
            System.out.println("ALICE_IS_OWNER: "
                + new PrincipalSid("alice").equals(acl.getOwner()));
            System.out.println("ALICE_READ: " + readAllowed(acl));
            System.out.println("ALICE_CHANGE_ACL: " + canChangeAcl(acl));

            login("bob");
            System.out.println("BOB_READ: " + readAllowed(acl));
            System.out.println("BOB_CHANGE_ACL: " + canChangeAcl(acl));

            login("carol");
            System.out.println("CAROL_READ_DENY: " + readAllowed(acl));

            login("dave");
            System.out.println("DAVE_READ: " + readAllowed(acl));
            System.out.println("DAVE_CHANGE_ACL: " + canChangeAcl(acl));

            login("root", "ROLE_ACL_ADMIN");
            System.out.println("ROOT_READ: " + readAllowed(acl));
            System.out.println("ROOT_CHANGE_ACL: " + canChangeAcl(acl));
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

### 6.3. Chạy và đối chiếu kết quả

Vào thư mục chứa `build.gradle`, chạy bằng Gradle Wrapper:

```bash
./gradlew run
```

Trên Windows PowerShell:

```bash
.\gradlew.bat run
```

Nếu chưa có Gradle Wrapper, cần tạo nó bằng Gradle tương thích, hoặc dùng `gradle run` nếu đã cài. **Những dòng do `System.out.println` của chương trình in ra** (không tính output Gradle/logger) dự kiến là:

```text
ALICE_IS_OWNER: true
ALICE_READ: false
ALICE_CHANGE_ACL: true
BOB_READ: true
BOB_CHANGE_ACL: false
CAROL_READ_DENY: false
DAVE_READ: false
DAVE_CHANGE_ACL: true
ROOT_READ: false
ROOT_CHANGE_ACL: true
```

Diễn giải:

1. Owner của ACL đúng là `alice`.
2. `alice` có thể quản trị ACL theo owner nhưng không có ACE READ, nên không tự được đọc.
3. `bob` có ACE READ GRANT nhưng không có quyền sửa ACL.
4. `carol` gặp ACE READ DENY.
5. `dave` có ACE ADMINISTRATION GRANT, vì thế có thể được quản trị ACL; không có READ.
6. `root` có system authority để sửa ACL nhưng không có READ ACE.

**Lưu ý:** kết quả có thể phụ thuộc cấu hình role hierarchy, SID retrieval hoặc custom strategies nếu thay đổi ví dụ. Với cấu hình mặc định nêu trong source, những dòng boolean là mục tiêu kiểm chứng. Việc chương trình dựng `UsernamePasswordAuthenticationToken` đã authenticated **chỉ là kỹ thuật demo**, không được dùng làm phương pháp đăng nhập production.

### 6.4. JUnit test cho hai strategy

**`src/test/java/demo/AclStrategiesDemoTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.acls.domain.AclImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.core.context.SecurityContextHolder;

class AclStrategiesDemoTest {

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void aclOwnerDoesNotAutomaticallyReadContent() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        assertEquals(new PrincipalSid("alice"), acl.getOwner());
        AclStrategiesDemo.login("alice");
        assertFalse(AclStrategiesDemo.readAllowed(acl));
        assertTrue(AclStrategiesDemo.canChangeAcl(acl));
    }

    @Test
    void readAceDoesNotAllowAclMutation() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        AclStrategiesDemo.login("bob");
        assertTrue(AclStrategiesDemo.readAllowed(acl));
        assertFalse(AclStrategiesDemo.canChangeAcl(acl));
    }

    @Test
    void administrationAceIsNotReadPermission() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        AclStrategiesDemo.login("dave");
        assertFalse(AclStrategiesDemo.readAllowed(acl));
        assertTrue(AclStrategiesDemo.canChangeAcl(acl));
    }

    @Test
    void explicitDenyPreventsRead() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        AclStrategiesDemo.login("carol");
        assertFalse(AclStrategiesDemo.readAllowed(acl));
    }

    @Test
    void systemRoleCanManageButDoesNotImplicitlyRead() {
        AclImpl acl = AclStrategiesDemo.buildSample();

        AclStrategiesDemo.login("root", "ROLE_ACL_ADMIN");
        assertFalse(AclStrategiesDemo.readAllowed(acl));
        assertTrue(AclStrategiesDemo.canChangeAcl(acl));
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test gọi trực tiếp implementation ACL thật (`AclImpl`) nên kiểm tra hai strategy; không cần Spring AOP. Nếu chuyển sang `@PreAuthorize` ở một service Spring, phải có test khác dùng `@SpringBootTest` và `@WithMockUser` đi qua **Spring-managed proxy** để xác nhận Method Security interceptor có hiệu lực.

## 7. Đưa hai strategy vào cấu hình Spring ACL JDBC

Ví dụ trên chỉ tạo ACL trong RAM. Trong ứng dụng Spring Boot có ACL lưu database, hai strategy thường được wire vào `BasicLookupStrategy` và `SpringCacheBasedAclCache` để ACL được load có behavior nhất quán.

Sơ đồ:

```text
HTTP / service method / scheduler
          |
          +-- đọc object -----------------------+
          |                                    |
          |                             AclPermissionEvaluator
          |                                    |
          |                                 AclService
          |                                    |
          |                                    v
          |                             BasicLookupStrategy
          |                                    |
          |                           AclImpl + ACE/owner/parent
          |                                    |
          |                             PermissionGrantingStrategy
          |
          +-- cập nhật ACL --------------------+
                                               |
                                        MutableAclService
                                               |
                                          AclImpl mutator
                                               |
                                        AclAuthorizationStrategy
                                               |
                                           updateAcl
```

### 7.1. Configuration minh họa

File **`AclConfiguration.java`** dưới đây là cấu hình Spring Boot, **không phải ứng dụng hoàn chỉnh** nếu chưa có datasource, SQL schema, Spring ACL dependencies và identity/policy phù hợp:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclConfiguration {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator evaluator) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
        );
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy grants,
            AclAuthorizationStrategy aclChanges) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"), grants, aclChanges);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache aclCache,
            AclAuthorizationStrategy aclChanges,
            PermissionGrantingStrategy grants) {
        return new BasicLookupStrategy(
            dataSource, aclCache, aclChanges, grants);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookupStrategy,
            AclCache aclCache) {
        return new JdbcMutableAclService(
            dataSource, lookupStrategy, aclCache);
    }
}
```

**Vì sao dùng `static @Bean` cho handler?** Method Security cần expression handler sớm khi khởi tạo cấu hình bảo mật. `setPermissionEvaluator` nối biểu thức `hasPermission(...)` với `AclPermissionEvaluator`. Nếu không nối, `@PreAuthorize("hasPermission(...)")` không mặc nhiên biết dùng ACL bạn đã lưu.

### 7.2. Dependency và schema

Với một Spring Boot Gradle project đã có Boot plugin/BOM, phần dependency tiêu biểu là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.security:spring-security-acl'
    implementation 'org.springframework:spring-context-support'
    runtimeOnly 'com.h2database:h2'
}
```

Đây là **mảnh Gradle**; muốn chạy cần version plugin, `repositories`, driver và các cấu hình dự án tương ứng. Trong production hãy dùng driver/schema/SQL phù hợp database thực tế, không nhất thiết H2.

Các bảng ACL cơ bản:

| Bảng | Chức năng |
| --- | --- |
| `acl_sid` | Lưu principal SID và granted-authority SID |
| `acl_class` | Loại domain object |
| `acl_object_identity` | Object ID, owner SID, ACL parent, inheritance |
| `acl_entry` | ACE order, SID, permission mask, granting và audit flags |

`JdbcMutableAclService` đảm nhận cập nhật ACL; `BasicLookupStrategy` phục vụ đọc ACL, có thể kết hợp `AclCache`. Cần khởi tạo đúng schema/sequence/ID identity do thư viện/dialect yêu cầu; chỉ tạo bảng tên giống nhau chưa bảo đảm mọi query hoạt động.

### 7.3. Mẫu Method Security

Khi đã có `AclPermissionEvaluator` và expression handler:

```java
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
public Document readDocument(Long id) {
    return documentRepository.findById(id).orElseThrow();
}
```

Đây là **mảnh service**; `Document`, repository và annotation import phải có trong dự án. `demo.Document` cần khớp type dùng trong ACL `ObjectIdentity`, thường là class name hoặc mapping tùy cấu hình. `@PreAuthorize` phải được bật với `@EnableMethodSecurity`; caller phải gọi qua bean/proxy.

Một user được cấp `ROLE_ACL_ADMIN` theo chiến lược sửa ACL **không tự được READ** trong biểu thức trên nếu ACL không có grant hoặc policy đọc tương ứng.

## 8. Service quản trị ACL cần kiểm tra nhiều hơn strategy

Đừng mở một API `grantRead(documentId, recipientId)` chỉ vì mutator sẽ gọi `AclAuthorizationStrategy`. Cần bảo vệ **cấp chức năng**, **phạm vi tài nguyên**, **recipient** và **quyền được grant**.

Một cấu trúc service:

```java
// Mảnh minh họa bên trong bean/service có các dependency đã inject.

@PreAuthorize("hasAuthority('acl:manage')")
public void grantRead(Long documentId, String recipientId) {

    // 1. Bản ghi thật từ server, không tin owner/tenant do client khai.
    Document document = documentRepository.require(documentId);

    // 2. Caller phải được quản trị tài liệu trong tenant này.
    tenantPolicy.requireCanManage(
        SecurityContextHolder.getContext().getAuthentication(),
        document
    );

    // 3. Chỉ cấp cho recipient hợp lệ theo policy.
    recipientPolicy.requireEligible(recipientId, document);

    ObjectIdentity identity =
        new ObjectIdentityImpl("demo.Document", documentId);

    MutableAcl acl = (MutableAcl)
        mutableAclService.readAclById(identity);

    int position = acl.getEntries() == null
        ? 0
        : acl.getEntries().size();

    // Mutator này có kiểm tra AclAuthorizationStrategy.
    acl.insertAce(
        position, BasePermission.READ,
        new PrincipalSid(recipientId), true
    );

    mutableAclService.updateAcl(acl);
}
```

Đây **không phải đoạn code độc lập**: cần các lớp `Document`, repository, `tenantPolicy`, `recipientPolicy`, `mutableAclService`, import và transaction thực tế. Nó minh họa ranh giới trách nhiệm:

- `@PreAuthorize` bảo vệ quyền **vào chức năng**.
- `tenantPolicy` bảo vệ **đúng tài nguyên và tenant**.
- `recipientPolicy` bảo vệ **đúng người được cấp quyền**.
- `AclAuthorizationStrategy` bảo vệ **thao tác sửa ACL**.
- `MutableAclService.updateAcl` lưu thay đổi và tương tác với cache.

Dùng `Aop` method security vẫn có giới hạn self-invocation: nếu method bảo vệ được gọi qua `this.grantRead(...)` trong cùng bean, interceptor có thể bị bỏ qua. Thiết kế service tách ranh giới và kiểm thử qua Spring proxy.

### Admin ACL vẫn có thể tự nâng quyền

Dù `BasePermission.ADMINISTRATION` không tự đồng nghĩa READ, người có quyền thêm ACE có thể tự thêm:

```text
PrincipalSid("admin") + READ GRANT
```

Nếu chức năng cho phép thao tác đó, user sẽ có quyền đọc ở các lần kiểm tra sau. Đây là **khả năng gián tiếp**, không phải behavior tự động của `PermissionGrantingStrategy`. Những ứng dụng chứa dữ liệu mật có thể cần maker–checker, cấm tự cấp, whitelist recipient, giới hạn quyền grant và audit đầy đủ.

## 9. Các trường hợp ảnh hưởng kết quả cấp quyền

### 9.1. ACL cha và inheritance

Một folder có `ROLE_TEAM` được READ, một document có parent ACL là folder. Nếu document `entriesInheriting=true` và không có quyết định local phù hợp, permission strategy có thể xét ACE của ACL cha. Nếu `entriesInheriting=false`, chỉ nối parent không làm ACE tự chảy xuống.

ACL owner của parent **không tự thành** ACL owner của child; quyền sửa ACL của child cần kiểm tra theo policy quản trị của child.

### 9.2. SID chỉ nạp một phần

`AclService.readAclById(identity, sids)` có thể trả một ACL chỉ nạp SID được yêu cầu. Khi đánh giá SID khác, `Acl.isGranted(...)` có thể ném `UnloadedSidException`. Đây không phải `false` có thể bỏ qua tùy tiện; cần nạp dữ liệu phù hợp và fail closed.

Khi làm UI quản trị ACE hoặc cập nhật ACL, cần đọc đầy đủ entries/SIDs phù hợp để tránh ghi đè hoặc bỏ sót ACE chưa nạp.

### 9.3. Deny, mask và thứ tự

Không biến mọi ACE có `granting=true` thành quyền chung. Strategy mặc định xét permission/SID/ACE theo quy tắc cụ thể, với khác biệt so mask ở nhánh grant và deny. Phải thử các case:

- Chỉ có READ GRANT.
- Chỉ có READ DENY.
- Có cả grant/deny cùng người hoặc qua nhiều SID.
- Permission là mask kết hợp.
- Có parent ACL grant trong khi local ACL chưa quyết định.
- Có parent ACL nhưng `entriesInheriting=false`.

### 9.4. Anonymous, role và tenant

`AnonymousAuthenticationToken` có thể báo `isAuthenticated()=true`; nếu viết custom strategy/guard, đừng chỉ dùng một check này để cho phép. `PrincipalSid("bob")` cũng có thể trùng giữa tenant nếu hệ thống dùng username không duy nhất. Nên chọn stable user ID và tenant namespace đáng tin, thống nhất với cách lưu ACE.

Không nhận actor/tenant/role từ request body rồi dùng làm security identity. Trong thực tế, identity đến từ `Authentication` do provider xác thực và mapping server.

## 10. Transaction, cache, audit và nhất quán

### 10.1. Cập nhật ACL và domain object là hai thao tác khác nhau

`acl.insertAce(...)` thay đối tượng ACL trong RAM; `mutableAclService.updateAcl(acl)` mới ghi thay đổi qua persistence layer. Thay domain owner không tự cập nhật ACL owner hoặc ACE.

Khi chuyển sở hữu cần xác định rõ:

1. Ai được đổi domain owner?
2. Có đổi ACL owner không?
3. Cấp grant mới gì cho owner mới?
4. Thu hồi ACE của owner cũ hay vẫn giữ share?
5. Có cập nhật parent ACL, tenant hoặc group memberships không?
6. Transaction, rollback, audit và cache invalidation ra sao?

### 10.2. Cache ACL và thu hồi quyền

`SpringCacheBasedAclCache` có thể giữ ACL đã nạp. Sau đổi owner, ACE hoặc inheritance, cache tương ứng phải được invalidation/cập nhật. Trong hệ thống nhiều node, một cache cục bộ ở node A không tự xóa cache của node B.

Không cache một boolean `allowed=true` chỉ theo `documentId`: quyết định phụ thuộc principal/SID, tenant, permission và ACL version. Khi quyền bị thu hồi, cache stale có thể làm người dùng tiếp tục truy cập trái phép.

### 10.3. TOCTOU và transaction

Khi kiểm tra `@PreAuthorize` ở thời điểm T1 rồi database cập nhật ở T2, ACL/owner có thể thay đổi ở giữa. Đó là rủi ro **time of check, time of use**. Với lệnh ghi nhạy cảm, cân nhắc lock, version, điều kiện UPDATE và transaction nhất quán để quyền được kiểm tra sát thời điểm ghi.

Không giả định chỉ cần `@Transactional` là tự động bảo đảm authorization không đổi giữa hai thời điểm; isolation và thiết kế DB quyết định hành vi.

### 10.4. N+1 ACL lookup

`@PostFilter("hasPermission(filterObject, 'READ')")` trên danh sách lớn có thể nạp ACL từng object. Sử dụng `AclService.readAclsById(...)`, batch retrieval hoặc truy vấn lọc quyền ở tầng dữ liệu nếu phù hợp. Không vì tối ưu mà bỏ qua deny, tenant, parent hay sid ordering.

### 10.5. Audit phải phân biệt hai sự kiện

- **ACL administration audit:** ai thêm/xóa ACE, đổi owner, đổi audit flags, thay parent, grant cho ai và trước/sau ra sao.
- **Permission decision audit:** ai đã yêu cầu READ/WRITE, trên object nào và kết quả allow/deny.

`administrativeMode` của `PermissionGrantingStrategy` liên quan việc audit permission checks; nó không thay thế logging riêng cho các thao tác chỉnh ACL. Không ghi credentials hoặc toàn bộ payload nhạy cảm.

## 11. Lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `AclAuthorizationStrategy` để xét READ | Chủ ACL bị cấp quyền đọc không chủ ý | Dùng `Acl.isGranted`/`AclPermissionEvaluator` |
| Dùng `PermissionGrantingStrategy` thay policy sửa ACL | READ ACE có thể bị nhầm thành admin | Mutator đi qua `securityCheck(changeType)` |
| Coi ADMINISTRATION là superuser dữ liệu | Mở quyền READ/DELETE ngoài yêu cầu | Định nghĩa permission theo từng hành động |
| Hiểu `administrativeMode=true` là cấp quyền admin | Sai quyết định/audit | Đặt quyền trong permission list |
| Dùng `[READ, WRITE]` như phép AND | Có thể cho phép khi chỉ một quyền được grant | Kiểm tra riêng, tổng hợp AND |
| Bỏ qua `NotFoundException`/`UnloadedSidException` | Quyền được xét từ dữ liệu thiếu | Fail closed, nạp đúng SID |
| Quên parent ACL | Kết quả cho phép/từ chối không khớp | Kiểm tra inheritance |
| Tự quét ACE và `anyMatch` | Mất deny/mask/order | Dùng strategy đúng |
| Cấp `ROLE_ACL_ADMIN` quá rộng | Có thể quản trị nhiều tenant | Scope quyền cấp hệ thống và policy service |
| Admin tự cấp READ | Nâng quyền gián tiếp | Kiểm soát grant/recipient, maker–checker |
| Không gắn strategy vào lookup/cache | ACL lấy từ các đường khác có behavior lệch | Wiring bean nhất quán |
| Sai `ObjectIdentity` | Lạc ACL, lộ quyền chéo object | Thống nhất type + ID |
| SID username trùng tenant | Trộn principal | Stable scoped SID |
| Thay ACL trực tiếp bằng SQL | Bỏ qua mutator guard | Bảo vệ DB và API, audit |
| Không invalidation sau revoke | Cho phép theo ACE cũ | Invalidate ACL cache/distributed cache |
| Self-invocation khi dùng Method Security | Bypass `@PreAuthorize` | Tách bean, test proxy |
| Chỉ test admin allow | Không phát hiện quyền cấp quá rộng | Test owner, reader, deny, missing, anonymous |

## 12. Bài tập tự đánh giá

1. **`AclAuthorizationStrategy` giải quyết câu hỏi nào?**  
   Ai được phép sửa danh sách ACL, bao gồm owner, ACE và audit theo loại thay đổi.

2. **`PermissionGrantingStrategy` giải quyết câu hỏi nào?**  
   ACL hiện tại có grant/deny permission được yêu cầu cho tập SID trên domain object hay không.

3. **User là ACL owner nhưng không có READ ACE: có tự được READ không?**  
   Không. Quyền quản trị ACL và quyền đọc dữ liệu tách biệt.

4. **User có READ ACE có được `insertAce(...)` không?**  
   Không mặc định; `AclAuthorizationStrategy` phải cho phép thao tác.

5. **`BasePermission.ADMINISTRATION` đồng nghĩa `READ` không?**  
   Không. Nó là mask độc lập, có thể là căn cứ quản trị ACL theo implementation mặc định.

6. **Một-authority và ba-authority constructor khác nhau thế nào?**  
   Một authority cấp quyền hệ thống cho cả ba nhóm change; ba authority chia tương ứng ownership, auditing, general.

7. **`administrativeMode=true` có cấp permission ADMINISTRATION không?**  
   Không. Boolean chủ yếu tác động audit; permission được yêu cầu nằm trong danh sách.

8. **`isGranted([READ, WRITE], sids, false)` là OR hay AND?**  
   Không nên xem là AND; strategy có thể cho phép khi một permission được cấp.

9. **Không tìm thấy ACE phù hợp thì luôn trả `false`?**  
   Không. `DefaultPermissionGrantingStrategy` có thể xét ACL cha hoặc ném `NotFoundException`.

10. **Đổi ACL owner có tự chuyển owner nghiệp vụ không?**  
    Không. Domain owner và ACL owner là hai nguồn dữ liệu riêng.

11. **Tại sao system ACL admin có thể gây rủi ro dù chưa có READ?**  
    Vì người đó có thể thêm ACE READ cho chính mình nếu policy grant không giới hạn.

12. **Test nào chứng minh hai strategy không bị trộn?**  
    Test ACL owner được sửa ACL nhưng không READ; reader có READ nhưng không sửa ACL; admin ACE có thể quản trị mà không READ; role admin hệ thống không tự có READ.

## 13. Tài liệu chính thức

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): thành phần ACL/JDBC, cách wire `BasicLookupStrategy`, cache và Method Security.
- [Spring Security 6.5 — `AclAuthorizationStrategy`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclAuthorizationStrategy.html): hợp đồng `securityCheck`, `CHANGE_GENERAL`, `CHANGE_OWNERSHIP`, `CHANGE_AUDITING`.
- [Spring Security 6.5 — `AclAuthorizationStrategyImpl`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclAuthorizationStrategyImpl.html): ACL owner, system authority, ACE administration và thứ tự authority constructor.
- [Spring Security 6.5 — `PermissionGrantingStrategy`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/PermissionGrantingStrategy.html): API `isGranted`.
- [Spring Security — `DefaultPermissionGrantingStrategy`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): thứ tự permission/SID, bitmask match, deny và parent.
- [Spring Security 6.5 — `AclImpl`](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/AclImpl.html): constructors, mutator methods, `isGranted`, SID và owner.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `hasPermission` và expression handler.

**Kết luận:** `AclAuthorizationStrategy` kiểm soát **ai có thể thay ACL**, còn `PermissionGrantingStrategy` quyết định **ai được dùng tài nguyên theo ACE/SID/permission**. Cả hai được `AclImpl` dùng, nhưng kết quả của cái này không tự thay thế cái kia. Trong ứng dụng thật, cần bổ sung policy tenant, bảo vệ service, kiểm tra recipient, kiểm thử deny/owner/admin và quản lý transaction/cache/audit.