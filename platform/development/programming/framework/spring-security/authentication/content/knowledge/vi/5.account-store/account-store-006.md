# Giao dịch đọc tài khoản và tránh phụ thuộc vào phiên ORM sau xác thực

## 1. Vấn đề cốt lõi: xác thực thành công không có nghĩa phiên ORM còn mở

Trong ứng dụng Spring Boot + Spring Security + Spring Data JPA, `UserDetailsService.loadUserByUsername(...)` thường truy vấn một tài khoản từ cơ sở dữ liệu. Bản ghi tài khoản có thể chứa mối quan hệ với danh sách vai trò (`roles`), quyền (`permissions`), tổ chức, trạng thái khóa, ... được ánh xạ thành **JPA entity**. Nhiều quan hệ được cấu hình **lazy loading**, nghĩa là Hibernate có thể chỉ tải dữ liệu khi code thực sự truy cập thuộc tính đó.

Điều này tạo ra một bẫy: **phiên ORM (Hibernate `Session` / JPA `EntityManager`) phục vụ giao dịch đọc user có thể kết thúc trước khi Spring Security sử dụng principal và authorities ở những giai đoạn tiếp theo**. Nếu `Authentication.getPrincipal()` giữ một entity hoặc `UserDetails.getAuthorities()` truy cập collection lazy từ entity đã detached, ứng dụng có thể ném `LazyInitializationException`, hoặc âm thầm tạo SQL ở những lớp không đáng lẽ phải truy vấn cơ sở dữ liệu.

**Mục tiêu thiết kế:**

1. Đọc tài khoản và mọi thông tin cần cho xác thực trong **một ranh giới giao dịch đọc rõ ràng**.
2. Chuyển dữ liệu cần thiết sang **`UserDetails`/security principal độc lập với JPA entity**, không giữ proxy hay collection lazy.
3. Kết thúc giao dịch đọc; `DaoAuthenticationProvider` và `SecurityContext` vẫn sử dụng principal/authorities đã có mà **không yêu cầu EntityManager tiếp tục mở**.
4. Nếu code nghiệp vụ cần dữ liệu người dùng mới nhất, truy vấn trong **giao dịch nghiệp vụ riêng**, dựa trên user ID/identity ổn định; không dùng principal như đối tượng entity sống xuyên suốt phiên đăng nhập.

**Một câu để nhớ:** *Giao dịch ORM dùng để nạp và kiểm tra dữ liệu tại một thời điểm; `Authentication` là một ảnh chụp danh tính phục vụ bảo mật, không phải một phiên ORM kéo dài qua các request.*

## 2. Phân biệt những khái niệm dễ bị gộp nhầm

| Khái niệm | Chức năng | Vòng đời thường gặp |
| --- | --- | --- |
| HTTP request | Một lần gọi API/trang web. | Bắt đầu khi nhận HTTP, kết thúc khi trả response. |
| Spring Security `SecurityContext` | Giữ `Authentication` hiện hành để kiểm tra quyền. | Theo request và có thể được lưu/khôi phục bằng cơ chế session/token tùy cấu hình. |
| `Authentication` / principal | Danh tính đã được xác thực cùng authorities. | Có thể vượt qua phạm vi giao dịch JPA và thậm chí qua nhiều request. |
| `UserDetailsService` | Tìm dữ liệu tài khoản cho `DaoAuthenticationProvider`. | Được gọi khi cơ chế username/password cần nạp user. |
| Spring `@Transactional` | Xác định ranh giới của một đơn vị công việc liên quan dữ liệu. | Theo lời gọi qua transaction proxy, không đồng nghĩa với thời gian tồn tại của HTTP session. |
| JPA `EntityManager` / Hibernate `Session` | Quản lý persistence context, entity và lazy loading. | Gắn với transaction hoặc cơ chế quản lý request cụ thể. |
| JPA entity managed/detached | Object ORM đang được quản lý hoặc đã tách khỏi persistence context. | Có thể chuyển sang detached sau khi transaction/context kết thúc. |
| `open-in-view` (OSIV) | Giữ EntityManager liên kết với một phần vòng đời web để hỗ trợ lazy load ngoài service transaction. | Phụ thuộc cấu hình; không phải contract của `UserDetailsService` hay security principal. |

Không có quan hệ 1-1 cố định giữa **HTTP request**, **SecurityContext**, **database transaction** và **ORM Session**. Một request có thể thực hiện nhiều giao dịch; một authentication có thể sống qua nhiều request; một entity có thể detached ngay khi giao dịch kết thúc.

### Vì sao vấn đề thường chỉ xuất hiện khi deploy/test?

- Test chạy với `@Transactional` bao quanh cả phương thức test nên entity vẫn managed; production kết thúc transaction sớm hơn.
- Môi trường development bật `spring.jpa.open-in-view=true`, controller hoặc serializer vẫn có thể lazy-load; khi tắt OSIV, lỗi lộ ra.
- Code dùng `@EntityGraph` hoặc `JOIN FETCH` ở một đường đi nhưng không có ở đường đi khác.
- Principal được cất trong session; một request sau đọc authorities khi EntityManager cũ đã đóng.
- Trường roles trước kia được cấu hình `EAGER` rồi đổi sang `LAZY` để tối ưu truy vấn mà chưa thay adapter xác thực.

Đừng “sửa” bằng cách buộc mọi quan hệ của entity thành `EAGER` hoặc kéo dài transaction qua toàn bộ session của người dùng. Hãy thiết kế đúng ranh giới.

## 3. Tình huống lỗi: trả JPA entity (hoặc wrapper giữ entity) làm UserDetails

Giả sử `AccountEntity` có quan hệ `roles` kiểu `@ManyToMany(fetch = FetchType.LAZY)`.

**Mẫu có vấn đề — chỉ là mã minh họa, không phải class hoàn chỉnh:**

```java
@Service
class UnsafeUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    UnsafeUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        AccountEntity entity = accounts.findByUsernameKey(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Account not found"));

        // CustomEntityUserDetails chỉ giữ tham chiếu tới JPA entity.
        // Nó KHÔNG tạo snapshot authorities ở đây.
        return new CustomEntityUserDetails(entity);
    }
}
```

Nếu `CustomEntityUserDetails.getAuthorities()` gọi `entity.getRoles().stream()`, khi provider hỏi quyền **sau khi method `loadUserByUsername` đã trả về**, có thể đã không còn persistence context dùng để khởi tạo lazy collection:

```text
loadUserByUsername()  [@Transactional(readOnly = true)]
  |
  +-- query AccountEntity (roles chưa được khởi tạo)
  +-- return CustomEntityUserDetails(entity)
  |
  +-- transaction/EntityManager đóng hoặc entity detached
  v
DaoAuthenticationProvider / AbstractUserDetailsAuthenticationProvider
  |
  +-- gọi getAuthorities() để tạo Authentication
      |
      +-- wrapper đòi entity.getRoles() [LAZY]
          |
          +-- LazyInitializationException (nếu không còn session)
```

**Ghi chú về thời điểm:** `DaoAuthenticationProvider` có thể kiểm tra account state và password trước khi cần authorities; vì vậy mật khẩu đúng chưa đủ để đảm bảo toàn bộ quá trình xây `Authentication` thành công. Thời điểm lỗi cụ thể tùy cách `UserDetails` được implement, thứ tự gọi và cấu hình persistence context.

Không có `LazyInitializationException` **không đồng nghĩa** thiết kế an toàn: với OSIV hoặc collection đã được khởi tạo từ trước, code vẫn chạy nhưng có thể thực hiện SQL bất ngờ hoặc để principal mang reference tới entity mutable.

### Mẫu rủi ro khác: lambda trong `getAuthorities()`

```java
class DatabaseBackedPrincipal implements UserDetails {
    private final AccountEntity account;

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        // Nguy hiểm: collection lazy và query có thể diễn ra rất muộn.
        return account.getRoles().stream()
                .map(role -> new SimpleGrantedAuthority(
                        "ROLE_" + role.getCode()))
                .toList();
    }

    // ... các method UserDetails khác
}
```

Mã trên là đoạn minh họa **không phải class Java độc lập**. Vấn đề không nằm ở toán tử `stream()` mà ở việc **để lộ proxy/lazy collection ra ngoài transaction**. Tương tự, `getUsername()`, `isEnabled()` hoặc `getPassword()` sẽ có vấn đề nếu chúng lấy dữ liệu từ một proxy chưa được khởi tạo.

## 4. Ranh giới mong muốn: read transaction → security snapshot → authenticate

Một thiết kế bền vững:

```text
HTTP login / Authentication filter
                |
                v
AuthenticationManager
                |
                v
DaoAuthenticationProvider
                |
                +--> UserDetailsService.loadUserByUsername(...)
                           |
                           | @Transactional(readOnly = true)
                           v
                    Repository tìm AccountEntity
                           |
                           +--> tải roles / trạng thái cần thiết
                           +--> validate các invariant của dữ liệu
                           +--> copy username, passwordHash,
                                enabled, locked, expired, authorities
                                vào UserDetails THUẦN, không giữ entity
                           |
                           v
                    return immutable/snapshot UserDetails
                           |
                    [transaction kết thúc]
                           |
                           v
          DaoAuthenticationProvider kiểm tra password + state
                           |
                           v
          Authentication chứa principal/authorities đã được dựng
                           |
                           v
             SecurityContext / authorization
                (KHÔNG dựa vào ORM Session vừa đóng)
```

Ba bước đặc biệt quan trọng:

1. **Nạp đủ dữ liệu cần thiết.** `roles`/`permissions` được fetch hoặc query bên trong cùng giao dịch, không dựa vào một lazy collection còn treo.
2. **Chuyển sang dữ liệu độc lập.** Có thể dùng `org.springframework.security.core.userdetails.User` của Spring Security hoặc một `UserDetails` tùy chỉnh chứa các trường scalar/collection immutable. Không mang JPA entity, `PersistentBag`, proxy hay `EntityManager` vào principal.
3. **Đặt một transaction ngắn quanh bước đọc–ánh xạ.** Giao dịch kết thúc trước khi authentication sống lâu hơn; sau đó password check dùng hash đã copy và authorities dùng snapshot.

### Vì sao snapshot không phải entity?

- Snapshot không thể tự mở SQL hoặc gọi `EntityManager` khi `getAuthorities()`.
- Snapshot dễ kiểm thử ngoài web container, không phụ thuộc OSIV.
- Principal trong session/serialization không mang theo toàn bộ graph dữ liệu, proxy Hibernate hay vòng tham chiếu.
- Security layer không thể vô tình mutate managed entity qua getter/setter.
- Truy vấn dữ liệu nghiệp vụ tiếp theo cần một service/repository có transaction riêng, với user ID ổn định.

Dù vậy, **snapshot có tính thời điểm**: nếu admin thu hồi role sau khi user đăng nhập, principal đã lưu trong session không nhất thiết tự thay đổi. Phần 11 phân tích cách làm mới quyền.

## 5. `@Transactional(readOnly = true)` thật sự bảo đảm điều gì?

Spring `@Transactional` tạo ranh giới giao dịch khi lời gọi đi qua **Spring proxy hoặc interception mechanism đã cấu hình**. Với `loadUserByUsername(...)`, có thể đặt annotation ở method public của bean do Spring quản lý:

```java
@Service
class JpaUserDetailsService implements UserDetailsService {

    // ... constructor và repository

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        // Tải và chuyển dữ liệu thành UserDetails ngay tại đây.
    }
}
```

`readOnly = true` là **gợi ý giao dịch và cơ hội tối ưu hóa**, không phải “khóa bảo mật cấm mọi câu INSERT/UPDATE”. Tùy driver, transaction manager, database và JPA provider, nó có thể điều chỉnh flush mode hoặc hint gửi xuống JDBC. Hệ quản trị cơ sở dữ liệu có thể thực thi read-only ở mức nhất định, nhưng không được giả định mọi thao tác ghi đều bị từ chối trong mọi môi trường.

**Bốn điều kiện thực tế để annotation hoạt động đúng:**

- Class/service phải là **bean Spring** được gọi thông qua interceptor/proxy phù hợp. Tự `new JpaUserDetailsService(...)` sẽ không kích hoạt transaction management.
- Phương thức được gọi từ **bên ngoài qua Spring proxy**; một lời gọi nội bộ `this.loadUserByUsername(...)` thường bỏ qua Spring proxy mặc định.
- Ứng dụng phải có transaction manager đúng cho JPA datasource; khi dùng nhiều datasource/transaction manager, cần chỉ định rõ manager hoặc qualifier nếu cần.
- Không ném dữ liệu lazy ra ngoài method rồi hy vọng transaction của service caller sẽ luôn còn mở. Bước ánh xạ phải hoàn tất **trước khi method trả về**.

### Giao dịch repository khác gì giao dịch service?

Spring Data JPA cấu hình giao dịch cho nhiều CRUD method kế thừa, nhưng **query method được khai báo riêng** không mặc nhiên nhận cùng transaction policy trong mọi trường hợp. Dù repository query có transactional, đặt một transaction ở **service** hữu ích hơn khi phải thực hiện nhiều bước: đọc user, đọc role, kiểm tra trạng thái, tạo snapshot.

Ví dụ nếu hai query cần thuộc một đơn vị đọc:

```java
@Transactional(readOnly = true)
public UserDetails loadUserByUsername(String username) {
    AccountEntity account = accounts.findByUsernameKey(username)
            .orElseThrow(() -> new UsernameNotFoundException("Not found"));

    List<String> permissions = permissionRepo
            .findPermissionCodesByAccountId(account.getId());

    // Cả hai query và phần xây snapshot nằm trong một transaction service.
    return buildSnapshot(account, permissions);
}
```

Đoạn trên **không chạy độc lập**: `permissionRepo` và `buildSnapshot` là thành phần ứng dụng. Transaction giúp điều phối đơn vị công việc, nhưng **không tự bảo đảm một snapshot nhất quán tại một thời điểm** nếu isolation level cho phép các truy vấn thấy thay đổi khác nhau. Với quyết định bảo mật cần tính nhất quán mạnh, cân nhắc cách query, isolation, locking và ranh giới nghiệp vụ theo yêu cầu.

## 6. Tải roles đúng lúc bằng `@EntityGraph` / `JOIN FETCH`

Giả sử data model:

```java
@Entity
@Table(name = "app_users")
class AccountEntity {
    @Id
    private Long id;

    @Column(name = "username_key", nullable = false, unique = true)
    private String usernameKey;

    @Column(name = "username_display", nullable = false)
    private String usernameDisplay;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    @Column(nullable = false)
    private boolean enabled;

    @Column(nullable = false)
    private boolean locked;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "account_roles",
        joinColumns = @JoinColumn(name = "account_id"),
        inverseJoinColumns = @JoinColumn(name = "role_id"))
    private Set<RoleEntity> roles = new HashSet<>();

    // getters; mapping đầy đủ và schema do dự án cung cấp.
}
```

`RoleEntity` chứa `id` và `code` (ví dụ `READER`, `EDITOR`). Đoạn entity trên là **minh họa**, bỏ qua constructors, schema, getters và imports để tập trung vào chiến lược đọc.

Trong repository:

```java
public interface AccountRepository
        extends JpaRepository<AccountEntity, Long> {

    @EntityGraph(attributePaths = "roles")
    Optional<AccountEntity> findByUsernameKey(String usernameKey);
}
```

Khi dùng JPA provider hỗ trợ entity graph, truy vấn này yêu cầu tải `roles` theo kế hoạch fetch cho **lời gọi cụ thể**. Tùy provider và mapping, ORM có thể dùng SQL join hoặc kế hoạch truy vấn khác; không nên khẳng định `@EntityGraph` *luôn* tạo đúng một SQL statement.

Một lựa chọn khác:

```java
@Query("""
    select distinct a
    from AccountEntity a
    left join fetch a.roles
    where a.usernameKey = :usernameKey
    """)
Optional<AccountEntity> findForAuthentication(
        @Param("usernameKey") String usernameKey);
```

`LEFT JOIN FETCH` giữ cả user chưa có role (để logic tiếp theo quyết định có chấp nhận không); `DISTINCT` ở JPQL giúp biểu đạt ý định không lặp account khi join collection. Nếu provider/SQL xử lý duplicate khác nhau, vẫn cần test bằng dữ liệu thực.

**Hạn chế của fetch join:**

- Tránh fetch nhiều collection dạng bag trong cùng query; Hibernate có thể gặp vấn đề multiple bags hoặc phát sinh dữ liệu nhân bản lớn.
- Tránh dựa vào collection fetch join khi phân trang dữ liệu lớn; bài toán nạp **một user cho authentication** khác với màn hình liệt kê hàng nghìn user.
- Không vội đổi mọi association thành `FetchType.EAGER`. Hãy lấy đúng dữ liệu cần cho từng use case.
- Nếu permission nằm sâu trong cây role → permissions, cần fetch/chiếu rõ tập authority cuối cùng; `roles` đã tải không có nghĩa `role.getPermissions()` cũng được tải.
- Đọc roles rồi copy thành `List/Set<GrantedAuthority>` **bên trong transaction**; chính nguyên tắc này làm code độc lập với chiến lược fetch cụ thể.

### Chọn query projection khi chỉ cần vài trường

Thay vì nạp cả entity graph, có thể query riêng dữ liệu cần dùng:

```java
// Trong repository, mã minh họa; cú pháp entity/field phải khớp dự án.
@Query("""
    select r.code
    from AccountEntity a
    join a.roles r
    where a.id = :accountId
    """)
List<String> findRoleCodes(@Param("accountId") Long accountId);
```

Trong transaction service, query user scalar và role code, tạo snapshot từ các giá trị đã materialize. Projection có thể giảm chi phí fetch graph phức tạp, nhưng có thể phát sinh nhiều round-trip và cần cân nhắc isolation. Không có phương án “luôn nhanh nhất”; hãy đo bằng SQL log/metrics và test dữ liệu.

## 7. Thiết kế `UserDetailsService` cụ thể: đọc entity và trả principal rời ORM

Sau đây là một **mẫu tích hợp** Spring Data JPA + Spring Security. Nó cố ý tách entity và principal, đặt `@Transactional(readOnly=true)` tại điểm đọc.

Giả định:

- `AccountEntity` có `getId()`, `getUsernameKey()`, `getUsernameDisplay()`, `getPasswordHash()`, `isEnabled()`, `isLocked()`, `getRoles()`.
- Mỗi `RoleEntity` có `getCode()` dạng `READER` (không có tiền tố).
- `AccountRepository.findByUsernameKey(...)` được khai báo với `@EntityGraph(attributePaths="roles")`.
- `UsernamePolicy.toKey(...)` là hàm normalization đúng policy của ứng dụng; cần áp dụng nhất quán ở đăng ký và lookup.
- `UserDetails` returned trong ví dụ là `User` của Spring Security; nếu cần ID nội bộ trong principal, xem phần 8.

```java
@Service
public class JpaAccountUserDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    public JpaAccountUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String inputUsername) {
        String usernameKey = UsernamePolicy.toKey(inputUsername);

        AccountEntity account = accounts.findByUsernameKey(usernameKey)
                .orElseThrow(() -> new UsernameNotFoundException(
                        "Account not found"));

        String[] authorities = account.getRoles().stream()
                .map(role -> "ROLE_" + role.getCode())
                .distinct()
                .sorted()
                .toArray(String[]::new);

        // COPY dữ liệu ra khỏi ORM ngay khi EntityManager còn hoạt động.
        return User.withUsername(account.getUsernameDisplay())
                .password(account.getPasswordHash())
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .authorities(authorities)
                .build();
    }
}
```

Cần các import `Service`, `Transactional`, `UserDetailsService`, `UserDetails`, `User`, `UsernameNotFoundException` và kiểu domain/repository do ứng dụng định nghĩa. Đoạn này **không phải class Java độc lập** vì không có toàn bộ entity/schema/config. Những phương thức `accountLocked(...)` và `disabled(...)` thuộc builder của Spring Security `User`. Nếu hệ thống còn trạng thái account expired, credentials expired, hãy truyền đầy đủ vào builder thay vì mặc định tất cả đều hợp lệ.

### Tại sao cách này tránh lazy session leak?

1. Query đọc account trong transaction.
2. `account.getRoles().stream()` chạy **trước khi method trả về**. Với graph hoặc lazy, role được materialize khi persistence context còn sẵn.
3. `String[] authorities` chứa các chuỗi role thuần Java.
4. `User.withUsername(...).password(...).authorities(...).build()` tạo `UserDetails` không tham chiếu `AccountEntity`, `RoleEntity` hay `Hibernate proxy`.
5. Sau khi transaction đóng, `DaoAuthenticationProvider` đọc passwordHash, status và authorities từ `User` độc lập; không có truy vấn ORM từ `getAuthorities()`.

**Lưu ý:** provider sẽ dùng `PasswordEncoder` được cấu hình để kiểm tra mật khẩu thô với hash lưu ở `passwordHash`. `UserDetailsService` chỉ nạp dữ liệu; không tự so password hay tự gọi `SecurityContextHolder.setContext`.

### Nếu không có role nào?

`UserDetailsService` và chính sách ứng dụng phải định nghĩa hành vi. Không được giả định mọi bản ghi có authorities. Với một số cấu hình, user không có `GrantedAuthority` có thể bị từ chối trong quá trình nạp/xác thực; nếu nghiệp vụ cho phép account không quyền, bạn phải xác định auth policy rõ ràng. **Không tự cấp `ROLE_USER` chỉ để tránh lỗi** khi dữ liệu DB đang thiếu quyền.

### Nếu có tên username khác case giữa request và DB?

Kết quả `UserDetails.getUsername()` có thể mang giá trị từ DB khác kiểu chữ đã nhập. API `UserDetailsService` cho phép implementation so case-sensitive hoặc case-insensitive; đừng dùng spelling raw của request để gán owner/authority. Áp dụng chính sách normalized key tại domain và giữ ID nội bộ ổn định.

## 8. Cần ID nội bộ trong principal? Dùng immutable snapshot thay vì entity

Spring Security `User` phù hợp nếu nghiệp vụ chỉ cần username, mật khẩu hash, flags và authorities. Nhưng nhiều hệ thống cần `accountId` ổn định để ghi audit và truy cập tài nguyên. Không vì vậy mà cất cả `AccountEntity` vào principal.

Một thiết kế tùy biến:

```java
public final class AccountPrincipal implements UserDetails {

    private final long accountId;
    private final String username;
    private String passwordHash;
    private final boolean enabled;
    private final boolean accountNonLocked;
    private final List<GrantedAuthority> authorities;

    public AccountPrincipal(
            long accountId,
            String username,
            String passwordHash,
            boolean enabled,
            boolean accountNonLocked,
            Collection<? extends GrantedAuthority> authorities) {

        this.accountId = accountId;
        this.username = Objects.requireNonNull(username);
        this.passwordHash = Objects.requireNonNull(passwordHash);
        this.enabled = enabled;
        this.accountNonLocked = accountNonLocked;
        this.authorities = List.copyOf(authorities);
    }

    public long getAccountId() { return accountId; }

    @Override public String getUsername() { return username; }
    @Override public String getPassword() { return passwordHash; }
    @Override public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }
    @Override public boolean isEnabled() { return enabled; }
    @Override public boolean isAccountNonLocked() { return accountNonLocked; }
}
```

Đây là **trích đoạn mô hình**, không phải class hoàn chỉnh cho mọi phiên bản/tình huống. Khi dùng trong production cần cân nhắc `Serializable` cho session persistence, vòng đời password hash, `CredentialsContainer.eraseCredentials()`, flags account/credentials expired, `equals/hashCode` khi cần, và khả năng thay đổi authorities. `List.copyOf` ngăn sửa cấu trúc list, nhưng không tự làm bất biến mọi object con; `SimpleGrantedAuthority` từ chuỗi role là một lựa chọn thuận tiện.

Nếu principal được đưa vào session hoặc cache, không nên giữ password hash lâu hơn cần thiết. `ProviderManager` mặc định cố xóa credentials từ authenticated result, nhưng **không có nghĩa mọi custom principal sẽ tự xóa `passwordHash`**. Cần kiểm tra phiên bản provider/manager, cách cache user và cơ chế xóa dữ liệu nhạy cảm. Không đưa `AccountEntity` chứa dữ liệu cá nhân đầy đủ vào principal cho tiện.

**Sự tách biệt hữu ích:**

- Principal: `accountId`, username, trạng thái và authorities cần cho authentication/authorization.
- Account entity: thông tin user trong DB, quan hệ ORM và transaction riêng.
- DTO response: tập dữ liệu được phép xuất ra cho client, không lộ password hash hoặc proxy.
- Audit event: user ID, hành động, thời điểm, kết quả; không lộ raw credentials.

## 9. Java 17 chạy độc lập: mô phỏng session boundary và snapshot

Để quan sát ranh giới mà **không phải khởi chạy JPA/Hibernate**, chương trình dưới đây mô phỏng lazy collection: một object đọc role cần session còn mở; một immutable snapshot được tạo khi session mở sẽ dùng được sau khi session đóng.

**Giới hạn quan trọng:** class `FakeSession` và `LazyRoles` **không phải API Hibernate**. Chúng chỉ minh họa điều kiện “dữ liệu chưa materialize + session đã đóng”. Trong ứng dụng thật, lỗi tương ứng có thể là `org.hibernate.LazyInitializationException` và thời điểm phụ thuộc ORM mapping.

Tạo file `OrmBoundaryDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public final class OrmBoundaryDemo {

    static final class FakeSession implements AutoCloseable {
        private boolean open = true;
        boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }

    static final class LazyRoles {
        private final FakeSession session;
        private final List<String> stored;
        private List<String> loaded;

        LazyRoles(FakeSession session, List<String> stored) {
            this.session = session;
            this.stored = List.copyOf(stored);
        }

        List<String> get() {
            if (loaded == null) {
                if (!session.isOpen()) {
                    throw new IllegalStateException("Lazy data unavailable");
                }
                loaded = List.copyOf(stored);
            }
            return loaded;
        }
    }

    static final class AccountEntityLike {
        final long id;
        final String username;
        final String passwordHash;
        final boolean enabled;
        final LazyRoles roles;

        AccountEntityLike(FakeSession session) {
            id = 42L;
            username = "lan";
            passwordHash = "demo-encoded-value";
            enabled = true;
            roles = new LazyRoles(
                    session, List.of("ROLE_READER", "document:read"));
        }
    }

    record SecuritySnapshot(
            long accountId,
            String username,
            String passwordHash,
            boolean enabled,
            List<String> authorities) {

        SecuritySnapshot {
            Objects.requireNonNull(username);
            Objects.requireNonNull(passwordHash);
            authorities = List.copyOf(authorities);
        }
    }

    static SecuritySnapshot loadInsideTransaction(
            AccountEntityLike entity) {

        // Materialize dữ liệu trước khi session đóng.
        List<String> copiedAuthorities = entity.roles.get();
        return new SecuritySnapshot(
                entity.id, entity.username, entity.passwordHash,
                entity.enabled, copiedAuthorities);
    }

    public static void main(String[] args) {
        // SAI: mang entity-like object đi, rồi mới hỏi lazy roles.
        AccountEntityLike unsafe;
        try (FakeSession session = new FakeSession()) {
            unsafe = new AccountEntityLike(session);
        }
        try {
            unsafe.roles.get();
            System.out.println("unsafe.afterClose=unexpected");
        } catch (IllegalStateException ex) {
            System.out.println("unsafe.afterClose=lazy-failed");
        }

        // ĐÚNG: ánh xạ thành snapshot trước khi session đóng.
        SecuritySnapshot principal;
        try (FakeSession session = new FakeSession()) {
            AccountEntityLike entity = new AccountEntityLike(session);
            principal = loadInsideTransaction(entity);
        }

        System.out.println("snapshot.user=" + principal.username());
        System.out.println("snapshot.id=" + principal.accountId());
        System.out.println("snapshot.enabled=" + principal.enabled());
        System.out.println("snapshot.authorities="
                + String.join(",", principal.authorities()));

        // Chứng minh list của snapshot không cho thêm role tùy ý.
        try {
            principal.authorities().add("ROLE_ADMIN");
            System.out.println("snapshot.mutable=true");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot.mutable=false");
        }

        System.out.println("snapshot.availableAfterClose=true");
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 OrmBoundaryDemo.java
java OrmBoundaryDemo
```

**Stdout chính xác do chương trình in ra:**

```text
unsafe.afterClose=lazy-failed
snapshot.user=lan
snapshot.id=42
snapshot.enabled=true
snapshot.authorities=ROLE_READER,document:read
snapshot.mutable=false
snapshot.availableAfterClose=true
```

Giải thích:

- Trong nhánh **unsafe**, session đã đóng trước khi lần đầu truy cập `LazyRoles.get()`; mô phỏng lazy loading thất bại.
- Trong nhánh **snapshot**, roles được tải/copy ngay trong `loadInsideTransaction`, trước khi session đóng. `SecuritySnapshot` không giữ `AccountEntityLike`, `LazyRoles` hoặc `FakeSession`.
- `List.copyOf` tạo list không sửa được; lệnh `add` cố sửa sẽ ném `UnsupportedOperationException`. Điều này giúp bảo vệ dữ liệu principal tránh bị cập nhật bừa bởi code nghiệp vụ.
- Bản mô phỏng không xác minh password, không dùng `DaoAuthenticationProvider` và không đụng cơ sở dữ liệu thật. Trong hệ thống Spring Security, snapshot được dùng làm `UserDetails` để provider kiểm tra password hash và trả authentication.

## 10. Spring Boot: không để OSIV che lỗi thiết kế xác thực

Trong ứng dụng Spring Boot JPA Servlet, thuộc tính:

```properties
spring.jpa.open-in-view=false
```

có thể được dùng để **tránh dựa vào EntityManager mở xuyên qua các phần của web request**. Khi tắt, mọi truy cập lazy ngoài transaction/persistence context hợp lệ sẽ lộ lỗi sớm hơn. Đây là một lựa chọn kiến trúc thường có lợi khi dùng service/DTO rõ ràng, nhưng phải đánh giá code đang sử dụng OSIV trước khi bật trong một dự án đã vận hành.

**OSIV không phải security boundary.** Bật OSIV có thể khiến lazy loading trong controller/serialization hoạt động ở vài luồng, nhưng:

- Nó không đảm bảo persistence context sẽ tồn tại **ở mọi điểm trong security filter chain**, mọi request hay mỗi tác vụ background.
- Nó không kéo dài EntityManager qua các request khác nhau trong cùng user session.
- Nó không đảm bảo code serialization không gây N+1 query hoặc truy vấn ngoài dự kiến.
- Nó không làm cho entity trở thành một security principal an toàn/immutable.
- Nó không thay thế `@Transactional` cho các đơn vị công việc đọc/ghi dữ liệu.

Nếu tắt OSIV và controller gặp lỗi do serializer đọc entity lazy, **đừng chỉ bật lại OSIV để “sửa” tất cả**. Hãy xác định endpoint/service nào phải fetch dữ liệu và map sang DTO trước khi trả response. Tương tự, nếu login lỗi do `getAuthorities()` đọc `roles` ngoài transaction, giải pháp là xây `UserDetails` đầy đủ trong giao dịch đọc, không dựa vào OSIV.

**Một mẫu cấu hình tiêu biểu**:

```properties
# Ranh giới ORM phải được quản lý bởi repository/service transaction.
spring.jpa.open-in-view=false

# Chỉ bật SQL debug có giới hạn ở môi trường test, không để lộ secret.
# logging.level.org.hibernate.SQL=DEBUG
```

Cấu hình này không tự tạo `UserDetailsService` hoặc bảo đảm repository đã fetch đủ quyền; cần kết hợp với adapter đúng.

## 11. Sau login, vai trò trong DB thay đổi thì snapshot ra sao?

Việc copy authorities vào principal giải quyết sự phụ thuộc vào ORM session, nhưng tạo một **bản chụp quyền tại thời điểm authentication**. Điều này cần được thiết kế với yêu cầu thu hồi quyền.

Ví dụ:

```text
T0: user "lan" đăng nhập, role = ROLE_EDITOR.
T1: Spring Security giữ Authentication trong HTTP session.
T2: admin rút ROLE_EDITOR khỏi DB.
T3: "lan" tiếp tục gửi request có session cũ.
```

Ở T3, principal trong session **có thể vẫn chứa ROLE_EDITOR** nếu ứng dụng không có cơ chế refresh/revalidation. Không có quy tắc Spring Security phổ quát rằng mọi request phải query lại `UserDetailsService`.

Các lựa chọn tùy nhu cầu:

| Cách | Lợi ích | Giới hạn |
| --- | --- | --- |
| Session ngắn hạn + xác thực lại | Đơn giản, giảm khoảng thời gian dữ liệu cũ. | Không thu hồi ngay lập tức khi thay quyền. |
| Invalidate/revoke session khi có sự kiện đổi quyền | Giảm nguy cơ quyền đã thu hồi còn hiệu lực. | Cần theo dõi session phân tán và sự kiện đáng tin cậy. |
| Version claim/authority version kiểm tra mỗi request hoặc khi cần | Dễ phát hiện snapshot cũ. | Có thể thêm cache/query; phải xử lý race và failure policy. |
| Authorization nghiệp vụ đọc dữ liệu mới tại mỗi thao tác nhạy cảm | Quyết định dựa vào trạng thái quyền mới nhất trong transaction nghiệp vụ. | Chi phí truy vấn và quy tắc nhất quán cần thiết kế. |
| Token ngắn hạn, refresh/revocation policy (JWT) | Kiểm soát cửa sổ hết hạn. | JWT tự chứa vẫn có thể hợp lệ đến khi hết hạn nếu không có cơ chế thu hồi. |

Khi cập nhật quyền/tài khoản, cần chọn chiến lược **thu hồi quyền thực tế**. Không “giải quyết” bằng cách nhét JPA entity vào principal rồi hy vọng nó tự refresh: entity detached không đảm bảo tự đồng bộ, còn phiên ORM kéo dài sẽ gây nhiều vấn đề hơn.

Một thực hành có giá trị: dùng `accountId` trong principal để service nghiệp vụ truy vấn tài nguyên/điều kiện hiện hành. Không dùng `username` hoặc dữ liệu lazy trong principal làm source of truth vĩnh viễn.

## 12. Transaction boundary không thay thế kiểm tra bảo mật trong nghiệp vụ

Có hai loại việc độc lập:

**Authentication-time read**

- Tìm username/user ID.
- Lấy password hash, trạng thái enabled/locked, authorities cơ bản.
- Trả `UserDetails` đã materialize.
- Provider kiểm tra password.
- Xác định principal và authorities ban đầu.

**Business-time authorization/read**

- Lấy đối tượng được yêu cầu theo ID.
- Đối chiếu owner, tenant, trạng thái object và policy.
- Dùng transaction nghiệp vụ phù hợp để đọc/ghi.
- Không chỉ dựa vào role snapshot nếu thao tác cần quyền theo dữ liệu hiện hành.

Ví dụ code nghiệp vụ:

```java
// Mã trích đoạn - cần entity, repository, chính sách tenant và
// AccountPrincipal do dự án định nghĩa.
@Transactional(readOnly = true)
public DocumentDto findDocument(long documentId, long accountId) {
    DocumentEntity document = documents.findById(documentId)
            .orElseThrow(DocumentNotFoundException::new);

    if (!document.getOwnerAccountId().equals(accountId)) {
        throw new AccessDeniedException("Forbidden");
    }

    return DocumentDto.from(document);
}
```

Đoạn trên không phải class chạy độc lập. Nó minh họa việc **kiểm tra owner + map DTO bên trong transaction nghiệp vụ**, dùng ID xác thực ổn định. Trong ứng dụng multi-tenant, cần kiểm tra cả tenant scope; nếu có race giữa kiểm tra quyền và ghi, cần thiết kế một transaction có khóa/điều kiện ghi đúng theo yêu cầu bảo mật.

Một service security principal **không cần giữ EntityManager mở** để cho phép nghiệp vụ thực hiện các truy vấn mới trong transaction riêng.

## 13. Xử lý hiệu năng: N+1, graph quá lớn và cache

### Không biến mỗi lần getAuthorities thành truy vấn

Nếu `getAuthorities()` truy cập lazy roles từ entity, các lần kiểm tra quyền có thể tạo SQL không dự đoán, N+1 hoặc lỗi detached. Với snapshot, danh sách quyền đã được materialize **một lần khi nạp user**.

Tuy nhiên, nạp role/permission quá sâu cũng gây hại:

- `JOIN FETCH` nhiều collection có thể nhân số dòng kết quả.
- Một account gắn hàng nghìn permission không nên mặc nhiên đưa toàn bộ domain object vào principal.
- Nếu permissions phụ thuộc tenant/resource, một flat list toàn cục có thể làm sai policy.
- Cần đánh giá có thực sự phải nạp permissions chi tiết trong login hay không; những quyền động có thể kiểm tra ở use case.

**Thực hành:** lập rõ “minimum authentication data set” gồm user ID/username, hash, flags và authorities cần cho policy tại bước đầu. Dùng projection hoặc entity graph có chủ đích. Chỉ tăng dữ liệu khi có nhu cầu và test.

### Cache UserDetails là một quyết định riêng

`UserCache` hoặc `CachingUserDetailsService` có thể tránh truy vấn lặp lại; nhưng cache làm phức tạp:

- Password hash có thể được xóa trong những object triển khai `CredentialsContainer` sau khi xác thực; dùng cùng instance trong cache có thể gây lỗi lần xác thực sau.
- Authorities/locked state trong cache có thể cũ sau cập nhật DB.
- TTL, invalidation, distributed cache và thay đổi quyền cần được thiết kế rõ.
- Nếu cache giữ principal có entity/lazy proxy, lỗi detached vẫn còn và khó tái hiện hơn.

**Không bật cache chỉ để che truy vấn ORM chưa tối ưu.** Giải quyết ranh giới snapshot trước, xác định chính sách freshness/revocation sau, rồi mới đánh giá cache.

### Audit SQL và số truy vấn

Bật thống kê/log SQL phù hợp trong môi trường thử nghiệm để xác nhận:

1. Đường login thực hiện những query user/role dự kiến.
2. `DaoAuthenticationProvider` không kích hoạt lazy query ngoài transaction qua `getAuthorities()`.
3. Sau khi `loadUserByUsername` trả về, các phép `getAuthorities()`/`getUsername()` trên principal không làm tăng số query JPA.
4. Controller/JSON serializer không cố duyệt entity được cất trong `Authentication`.

Tránh ghi toàn bộ request body, `Authorization` header, raw password hoặc token vào log khi đo hệ thống xác thực.

## 14. Kiểm thử đúng ranh giới transaction

Một test chỉ có `@Transactional` trên toàn bộ method **có thể che lỗi lazy loading**. Khi test method nằm trong transaction, code dễ truy cập collection sau repository mà vẫn có EntityManager. Production, đặc biệt khi trả principal cho security filter hoặc session, không nhất thiết có transaction như vậy.

### Bộ test nên có

| Test | Kịch bản | Mong đợi |
| --- | --- | --- |
| **Principal detached-safe** | Gọi `loadUserByUsername` qua Spring bean, sau khi method trả về truy cập `getAuthorities()`. | Đọc thành công, không tạo SQL JPA/lazy exception. |
| **Provider success** | Login đúng password qua `AuthenticationManager` + `DaoAuthenticationProvider`. | `Authentication` đã xác thực, authorities chính xác. |
| **Wrong password** | Login đúng username nhưng password sai. | Ném `BadCredentialsException`. |
| **Disabled user** | Account `enabled=false` trong DB. | Provider từ chối, thường bằng `DisabledException`. |
| **Roles lazy** | Entity `roles` được cấu hình `LAZY`, query fetch/mapper chạy đúng. | `UserDetails` sau khi return vẫn có roles hoàn chỉnh. |
| **OSIV off** | Test web với `spring.jpa.open-in-view=false`. | Controller/filter không cần ORM Session từ bước login để đọc principal. |
| **Query count** | Kiểm tra quyền lặp lại sau login. | Không phát sinh thêm query chỉ vì truy cập fields của principal. |
| **Role revocation** | Admin rút role của tài khoản đã có session. | Hành vi phù hợp chính sách refresh/revoke đã định nghĩa. |
| **Concurrency** | Hai request cập nhật role/login cùng thời điểm. | Kết quả nhất quán theo transaction isolation/revocation policy. |

### Mẫu integration test cần chú ý

```java
// Trích đoạn trong một @SpringBootTest test class đã inject
// UserDetailsService, AuthenticationManager, repository và seeded DB.
//
// Không đặt @Transactional lên toàn bộ test method nếu mục tiêu
// là chứng minh principal hoạt động sau service transaction.
@Test
void userDetailsAreIndependentAfterReadTransaction() {
    UserDetails user = userDetailsService.loadUserByUsername("lan");

    // Đã ra khỏi method loadUserByUsername, transaction của nó kết thúc
    // nếu không có transaction ngoài và Spring proxy hoạt động đúng.
    assertEquals("lan", user.getUsername());
    assertTrue(user.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
}
```

Đây **không phải test class đầy đủ**: cần dữ liệu mẫu, test integration thực với database, bean config và static imports. Nếu test framework hoặc method caller mở transaction ngoài, assertion vẫn có thể chạy trong context khác; phải cô lập ranh giới bằng cấu hình test phù hợp hoặc kiểm tra không có transaction tại thời điểm gọi principal sau load.

Một test bổ sung mạnh hơn có thể:

1. Gọi service qua Spring proxy.
2. Sau khi nó trả về, kiểm tra `TransactionSynchronizationManager.isActualTransactionActive() == false` trong test thread (khi không có transaction bao ngoài).
3. Kiểm tra `user.getAuthorities()` và mọi getter cần dùng.
4. Nếu muốn chắc rằng không đụng ORM, đo query count hoặc chạy với EntityManager đã clear/đóng theo cơ chế test hợp lệ.

**Đừng gọi `entityManager.close()` tùy tiện trên persistence context do Spring quản lý** để “ép” test; có thể phá môi trường test. Hãy dùng boundary/`TestTransaction`/transaction template hoặc query-count framework phù hợp.

### Vì sao test authorization với `@WithMockUser` chưa đủ?

`@WithMockUser` tạo `Authentication` giả phục vụ kiểm thử quyền, thường **bỏ qua `UserDetailsService` và database**. Test đó có thể xanh ngay cả khi `loadUserByUsername` giữ lazy entity và login thật sẽ lỗi. Cần ít nhất một test đi qua **manager/provider thật** và một test khẳng định `UserDetails` độc lập khỏi session sau khi tải.

## 15. Khi nào `@Transactional` ở service vẫn chưa đủ?

Ngay cả khi có annotation, lỗi vẫn xuất hiện nếu:

1. **Self-invocation:** method A trong cùng object gọi `this.loadUserByUsername()`; với proxy-based transactions, interceptor có thể không chạy.
2. **Bean không do Spring quản lý:** tạo bằng `new` thay vì dependency injection; không có proxy transaction.
3. **Mapping chưa materialize:** return entity/wrapper mà getAuthorities mới đọc lazy roles **sau khi method kết thúc**.
4. **Nested relation lazy:** chỉ fetch role nhưng permission nằm trong role còn lazy.
5. **Sai transaction manager:** query user dùng một datasource/EM khác transaction đang mở.
6. **Chạy async:** thread mới không tự kế thừa transaction/persistence context của thread gốc.
7. **OSIV phụ thuộc môi trường:** test web mở session còn production/background job không.
8. **Dữ liệu thay đổi đồng thời:** transaction `readOnly` không tự giải quyết mọi yêu cầu nhất quán giữa nhiều query.
9. **Custom principal giữ `Supplier`/callback gọi repository về sau:** có thể biến `getAuthorities()` thành thao tác phụ thuộc DB/transaction lúc authorization.
10. **Custom password encoder/service lại đọc entity lazy:** provider không chỉ gọi `getAuthorities()`; mọi đường truy cập dữ liệu trong auth phải độc lập sau service return.

**Cách sửa chung:** quyết định tập dữ liệu tối thiểu phải lấy, đặt ranh giới service transaction phù hợp, materialize toàn bộ tập ấy, trả immutable hoặc self-contained `UserDetails` rồi test ngoài transaction.

## 16. Một kiến trúc khuyến nghị có thể áp dụng

### Lớp dữ liệu

- `AccountRepository` trả `AccountEntity` hoặc projection có username key, hash, trạng thái và quyền cần thiết.
- Khi dùng entity, chỉ fetch association cho use case authentication, không đổi tất cả mapping thành EAGER.
- Unique constraint trên username/email key phù hợp chính sách đăng ký.
- Password hash phải dùng thuật toán lưu trữ phù hợp, không phải plaintext.

### Lớp adapter xác thực

- `@Service` triển khai `UserDetailsService`.
- `@Transactional(readOnly=true)` ở method public được Spring proxy gọi.
- Normalization/lookup theo policy dùng chung.
- Ánh xạ authorities ngay trong transaction.
- Trả `UserDetails` chỉ chứa Java value/collections và trạng thái cần thiết; không giữ entity/ORM proxy.
- Nếu không tìm thấy user, ném `UsernameNotFoundException`. Không tự trả `null` hay token đăng nhập giả.

### Lớp Spring Security

- `DaoAuthenticationProvider` dùng `UserDetailsService` cùng `PasswordEncoder` tương thích hash đang lưu.
- `ProviderManager`/`AuthenticationManager` xử lý thành công/thất bại.
- Filter chuẩn thiết lập `SecurityContext`; phần này khác với giao dịch đọc account.
- Authorization dùng authorities snapshot và policy nghiệp vụ phù hợp; không gọi lazy entity từ principal.

### Lớp nghiệp vụ

- Dùng ID tài khoản đã được xác thực, rồi mở transaction riêng để đọc/cập nhật tài nguyên.
- Kiểm tra owner/tenant/policy trên dữ liệu hiện hành khi cần.
- Trả DTO rõ trường; không expose entity/password hash qua JSON.
- Định nghĩa chiến lược invalidation quyền/khóa tài khoản để xử lý dữ liệu principal cũ.

Cấu hình thường có giá trị để phát hiện phụ thuộc ORM ngầm trong web:

```properties
spring.jpa.open-in-view=false
```

Đây là một **khuyến nghị thiết kế cần kiểm chứng**, không phải điều kiện cần cho mọi ứng dụng. Dù OSIV bật hay tắt, principal vẫn nên không giữ entity.

## 17. Những sai lầm thường gặp

1. **Giữ `AccountEntity` trực tiếp trong `Authentication.principal`.** Entity có thể detached, lazy hoặc chứa dữ liệu nhạy cảm; không phải security snapshot.
2. **Để `UserDetails.getAuthorities()` truy cập `entity.getRoles()`.** Có thể gây `LazyInitializationException` hoặc SQL muộn.
3. **Đặt `@Transactional` lên method nhưng trả wrapper giữ entity.** Annotation không giữ transaction sống sau khi method trả về.
4. **Bật OSIV để che mọi lỗi lazy khi login.** OSIV không mở ORM Session xuyên user session, không bảo đảm filter chain nào cũng có context.
5. **Đổi mọi quan hệ thành EAGER.** Có thể tăng chi phí, N+1 hoặc graph quá lớn; ưu tiên fetch theo use case.
6. **Dùng `@EntityGraph` rồi trả entity làm principal.** Graph giúp tải dữ liệu, nhưng vẫn chưa tách principal khỏi persistence model.
7. **Chỉ có repository transaction ngắn, mapping roles ở controller.** Đã ra ngoài transaction, các quan hệ lazy có thể hỏng.
8. **Tự `new` service có `@Transactional`.** Không có transaction proxy Spring.
9. **Gọi method annotated bằng `this.` trong cùng bean.** Self-invocation thường bypass proxy.
10. **Tin rằng `readOnly=true` là bảo mật chống ghi DB.** Đây là transaction hint/optimization, không phải access-control rule.
11. **Coi test `@Transactional` xanh là đủ chứng minh production an toàn.** Test transaction có thể che bug detached.
12. **Dùng `@WithMockUser` để kết luận login DB đúng.** Mock bỏ qua UserDetailsService/provider trong nhiều cấu hình.
13. **Nhét toàn bộ permissions/tenant object vào principal.** Tăng kích thước session, stale data và nguy cơ rò.
14. **Cache principal chứa JPA entity.** Cache không làm proxy trở nên an toàn; còn thêm nguy cơ dữ liệu cũ.
15. **Không tính cơ chế thu hồi quyền.** Snapshot đúng kỹ thuật nhưng vẫn cần policy làm mới role/session.
16. **Chỉ kiểm tra `hasRole` mà không kiểm tra owner dữ liệu.** Authorization theo resource là trách nhiệm độc lập.
17. **Ghi log toàn bộ `Authentication`/entity.** Có nguy cơ rò hash, PII hoặc graph dữ liệu.
18. **Cho rằng `EntityManager` và HTTP session là một.** Chúng có scope khác nhau; không được dùng thay cho nhau.
19. **Nhầm JPA read transaction với xác thực password.** Giao dịch chỉ nạp dữ liệu; provider mới so raw password với hash.
20. **Không kiểm tra consistency trong nhiều query.** Một transaction không bảo đảm một snapshot hoàn toàn nhất quán ở mọi isolation level.
21. **Bắt `LazyInitializationException` rồi trả roles rỗng.** Có thể khiến user mất quyền bất ngờ hoặc che lỗi dữ liệu; sửa cách fetch/map.
22. **Load roles bằng query khi `getAuthorities()` được gọi sau login.** Biến authorization thành DB I/O không kiểm soát, dễ sai scope và khó test.

## 18. Tự kiểm tra kiến thức

**Câu 1.** `loadUserByUsername` được đánh dấu `@Transactional(readOnly=true)`, nhưng trả `CustomUserDetails` giữ `AccountEntity`. `getAuthorities()` truy cập `entity.getRoles()` ở ngoài method. Có an toàn không?

**Trả lời:** Không. Method transactional đã kết thúc; entity/lazy collection có thể detached. Ánh xạ authorities sang Java collection và tạo self-contained UserDetails **trong transaction**.

**Câu 2.** Dùng `@EntityGraph(attributePaths="roles")` có tự làm principal độc lập với Hibernate?

**Trả lời:** Không. Graph giúp fetch quan hệ trong query, nhưng entity vẫn là object ORM. Cần copy các trường cần thiết và không giữ entity trong principal.

**Câu 3.** `readOnly=true` có bảo đảm driver/DB từ chối tất cả lệnh UPDATE không?

**Trả lời:** Không. Đây là hint/transaction configuration có thể tối ưu cách xử lý; không phải quy tắc bảo mật cấm ghi phổ quát.

**Câu 4.** Vì sao test có `@Transactional` trên toàn bộ test method dễ làm lỗi lazy không xuất hiện?

**Trả lời:** Persistence context có thể còn mở khi assertion truy cập lazy field. Cần test principal ở ngoài transaction để phản ánh ranh giới thực.

**Câu 5.** Nếu tắt `spring.jpa.open-in-view` thì login nhất định thất bại?

**Trả lời:** Không. Login được thiết kế đúng sẽ nạp tài khoản/quyền và chuyển thành UserDetails trong transaction, nên không phụ thuộc OSIV.

**Câu 6.** Admin xóa quyền `ROLE_EDITOR` trong database sau khi user đăng nhập. Principal trong session có tự cập nhật không?

**Trả lời:** Không được giả định. Principal là snapshot; cần chính sách refresh/revocation hoặc authorization nghiệp vụ đọc trạng thái mới.

**Câu 7.** Tại sao không dùng `Authentication.getPrincipal()` trả JPA entity để tránh truy vấn lại ở service nghiệp vụ?

**Trả lời:** Entity có thể detached, chứa lazy proxy, dữ liệu cũ/nhạy cảm, và không có transaction hợp lệ. Nghiệp vụ nên dùng user ID ổn định để truy vấn trong transaction riêng.

**Câu 8.** `UserDetailsService` chỉ cần trả `UserDetails` đúng username; tại sao phải copy password hash và flags?

**Trả lời:** `DaoAuthenticationProvider` cần mật khẩu đã encode và trạng thái account để kiểm chứng. Nếu getters đọc từ entity/proxy detached, xác thực có thể lỗi ngay trong provider.

**Câu 9.** Đưa `@Transactional` vào phương thức private hoặc gọi qua `this.` trong Spring proxy mode có đáng tin không?

**Trả lời:** Không. Hãy đặt ranh giới ở public service method của Spring bean được gọi qua proxy phù hợp; kiểm thử transaction thực tế.

**Câu 10.** Một query fetch role và permission chạy rất chậm vì nhiều collection. Có nên cứ dùng một `JOIN FETCH` khổng lồ?

**Trả lời:** Không nhất thiết. Cân nhắc projection, truy vấn tách có transaction service, giới hạn dữ liệu vào principal và tối ưu dựa trên SQL thực tế.

## 19. Tài liệu tham khảo chính thức

- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): mặc định transaction của các repository method, transactional query method, service boundary và ý nghĩa `readOnly`.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, proxy, cấu hình annotation và transaction semantics.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): khi nào interceptor/proxy xử lý giao dịch, self-invocation và các giới hạn.
- [Spring Data JPA — EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.entity-graph): kiểm soát fetch plan cho repository query.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): vai trò nguồn dữ liệu cung cấp `UserDetails`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): cách provider dùng user record, password encoder và authorities.
- [Hibernate ORM — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching): lazy/eager, join fetch và các lựa chọn fetch.
- [Spring Boot — JPA Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jpa-and-spring-data): cấu hình JPA trong Spring Boot, bao gồm hành vi liên quan OSIV theo phiên bản.

**Kết luận:** giao dịch đọc tài khoản nên là một **đơn vị làm việc ngắn, đầy đủ**: tìm account, nạp những thuộc tính/authority cần thiết, chuyển thành `UserDetails` độc lập rồi đóng giao dịch. Sau đó `Authentication`, `SecurityContext` và các tầng authorization không cần biết entity đã detached hay Hibernate Session đã đóng. Tránh phụ thuộc OSIV và không dùng JPA entity làm principal; đồng thời thiết kế riêng tính mới của quyền và giao dịch nghiệp vụ để bảo đảm an toàn khi người dùng tiếp tục hoạt động sau đăng nhập.