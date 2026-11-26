# Lập ma trận tài nguyên, hành động, danh tính và quyền

> **Chương:** Chiến lược kiểm thử  
> **Module:** `SPRING_SECURITY_TESTING` — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` cho ứng dụng Servlet và Reactive. Các ví dụ dùng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và danh tính JWT/OAuth2/OIDC giả lập.

## 1. Ma trận bảo mật là gì và giải quyết vấn đề nào?

Trong một ứng dụng, câu nói “người dùng đã đăng nhập thì được truy cập” thường không đủ để viết kiểm thử bảo mật. Người dùng **nào**, hành động **gì**, trên tài nguyên **của ai**, với **quyền nào** và trong **ngữ cảnh nào** là những câu hỏi khác nhau.

**Ma trận kiểm thử bảo mật** (*security test matrix*) là bảng mô tả các tổ hợp đầu vào và quyết định truy cập mong đợi. Mỗi dòng của bảng đại diện cho một ca kiểm thử có thể tái hiện được.

```text
                     DANH TÍNH / QUYỀN
                     Ẩn danh   USER   REPORT_READ   ADMIN
TÀI NGUYÊN  HÀNH ĐỘNG
/public      GET         ALLOW   ALLOW     ALLOW      ALLOW
/reports     GET         DENY    DENY      ALLOW      [theo policy]
/orders/42   DELETE      DENY    [theo owner/status/CSRF] ...
```

Bảng ví dụ trên chưa đủ chi tiết cho `DELETE /orders/42` vì quyết định còn phụ thuộc **chủ sở hữu**, **trạng thái đơn** và **CSRF token**. Một ma trận hữu ích phải đưa những điều kiện này thành các cột hoặc các biến thể có thể kiểm chứng, không đoán chúng từ vai trò.

Mục tiêu bài học là giúp người học:

- Xác định đúng các trục **tài nguyên × hành động × danh tính × quyền × điều kiện**.
- Phân biệt role, authority, OAuth2 scope và các thuộc tính như owner/tenant.
- Chọn các tổ hợp cho phép, từ chối và trường hợp biên mà không tạo hàng nghìn test vô ích.
- Chuyển dòng ma trận thành dữ liệu test và assertion cho Servlet/Reactive.
- Kiểm tra các quy tắc ở cả lớp HTTP và lớp service, bao gồm việc **không lộ dữ liệu** và **không gây tác động phụ** khi bị từ chối.

## 2. Năm trục cấu thành một dòng kiểm thử

Một dòng ma trận thường trả lời năm nhóm câu hỏi:

| Trục | Nội dung cần xác định | Ví dụ |
|---|---|---|
| **Tài nguyên** (*resource*) | Đường dẫn/API, loại đối tượng, ID, chủ sở hữu, tenant | `/api/orders/42`, owner = `an`, tenant = `acme` |
| **Hành động** (*action*) | HTTP method hoặc thao tác nghiệp vụ | `GET`, `POST`, `PATCH`, `DELETE`, `approveOrder` |
| **Danh tính** (*identity*) | Ẩn danh hay đã xác thực, principal là ai, cách xác thực | anonymous; `an` qua session; đối tác với Bearer JWT |
| **Quyền** (*permission*) | Role, authority, scope và cách ánh xạ thật | `ROLE_ADMIN`, `ORDER_DELETE`, `SCOPE_partner.read` |
| **Điều kiện** (*context*) | Owner, tenant, trạng thái đối tượng, CSRF, policy HTTP, thời điểm | cùng tenant, đơn `DRAFT`, CSRF hợp lệ |

Từ đó định nghĩa **quyết định mong đợi** (*expected decision*) và **bằng chứng kiểm tra** (*assertions*):

```text
Case = (resource, action, identity, permissions, context)
     -> (decision, HTTP response, observable side effects)

Ví dụ:
("/api/orders/42", DELETE, "binh",
 ["ORDER_DELETE"], owner="an"; tenant="acme"; csrf=VALID)
 -> DENY, 403, order 42 remains unchanged
```

Tài nguyên là **đối tượng chịu tác động**, không đơn thuần là chuỗi URL. Hai request `GET /api/orders/42` và `GET /api/orders/43` có thể khớp cùng một route nhưng đụng hai tài nguyên có chủ sở hữu khác nhau. Nếu chỉ kiểm thử URL pattern, ta dễ bỏ sót lỗi truy cập đối tượng không được phép (*Broken Object Level Authorization* hay BOLA/IDOR).

Hành động cũng cần ghi rõ: một tài nguyên có thể cho phép `GET` nhưng cấm `DELETE`. Có hệ thống dùng phương thức nghiệp vụ `approveOrder` hoặc `refundPayment` với quyền riêng dù cùng endpoint cập nhật.

### Phân biệt chính xác bốn khái niệm liên quan danh tính

**Xác thực (*authentication*)** cho biết yêu cầu có đại diện cho một principal hợp lệ không. **Phân quyền (*authorization*)** quyết định principal ấy được làm gì.

Role, authority và scope liên quan nhưng không đồng nhất:

- `roles = "ADMIN"` trong `@WithMockUser` thường cấp authority `ROLE_ADMIN` để phù hợp với `hasRole("ADMIN")`.
- `authorities = "REPORT_READ"` cấp chuỗi chính xác `REPORT_READ`, phù hợp với `hasAuthority("REPORT_READ")`.
- Scope OAuth2 `partner.read` trong resource server thường được ánh xạ thành `SCOPE_partner.read`; ứng dụng có thể thay đổi converter.
- `ownerId`, `tenantId` hay trạng thái đơn là **thuộc tính đối tượng/ngữ cảnh**, không tự động xuất hiện như một authority.

Ma trận cần thể hiện những khác biệt này. “Có quyền ADMIN” là mô tả chưa chặt nếu code thực thi `hasAuthority("ADMIN")` trong khi test cung cấp `ROLE_ADMIN`.

## 3. Dựng danh mục tài nguyên và hợp đồng nghiệp vụ

Xét ứng dụng quản lý đơn hàng có ba nhóm giao tiếp:

1. **Web/API dùng session hoặc cookie:** nhân viên và khách hàng truy cập đơn hàng, báo cáo; yêu cầu thay đổi trạng thái chịu CSRF protection.
2. **API đối tác dùng Bearer JWT:** đối tác đọc dữ liệu được phép qua OAuth2 resource server.
3. **Tài nguyên công khai:** danh mục sản phẩm để ai cũng truy cập.

Chọn các quy tắc minh họa:

| Tài nguyên | Hành động | Quy tắc cho phép | Điều kiện bổ sung |
|---|---|---|---|
| `/public/catalog` | `GET` | Mọi người | Không tiết lộ dữ liệu riêng |
| `/api/me` | `GET` | Principal đã xác thực | Chỉ trả dữ liệu của principal |
| `/api/reports` | `GET` | Có authority `REPORT_READ` | Dữ liệu báo cáo theo phạm vi đã cấp |
| `/api/orders` | `POST` | Người dùng đã xác thực | CSRF hợp lệ với phiên/cookie; dữ liệu hợp lệ |
| `/api/orders/{id}` | `GET` | Chủ đơn hoặc `ROLE_ADMIN` | Đơn thuộc tenant có thể truy cập |
| `/api/orders/{id}` | `DELETE` | Chủ đơn hoặc `ROLE_ADMIN` | CSRF hợp lệ; đơn ở trạng thái `DRAFT` |
| `/partner/data` | `GET` | JWT hợp lệ có scope `partner.read` | Dữ liệu chỉ thuộc đối tác/tenant được cấp |
| Các route khác | Tùy hành động | Từ chối theo chính sách mặc định | Ngoại lệ chỉ khi được khai báo rõ |

Đây là **hợp đồng ví dụ**, không phải mặc định áp dụng cho mọi dự án Spring Security. Trong một hệ thống khác, admin vẫn có thể bị ràng buộc tenant, chủ đơn có thể không được xóa, hoặc policy có thể trả `404` thay `403` để che giấu sự tồn tại của tài nguyên.

Đặt giả định HTTP rõ ràng từ đầu:

- Nhánh API ví dụ trả **`401` khi chưa xác thực**, **`403` khi đã xác thực nhưng thiếu quyền**, `200`/`201`/`204` khi thành công.
- Ứng dụng dùng form login thông thường có thể trả **`302`** đến trang đăng nhập cho người ẩn danh; trường hợp đó cần cập nhật kỳ vọng của ma trận.
- Với một thao tác hợp lệ về quyền nhưng bị chặn do **trạng thái nghiệp vụ** (`SETTLED`/`CLOSED`), ví dụ chọn `409 Conflict`; đừng trộn mọi lỗi nghiệp vụ vào `403`.
- Đối với thao tác thay đổi trạng thái qua session/cookie, CSRF là một tiền điều kiện độc lập với quyền.
- `GET /partner/data` đi qua resource server có decoder JWT và scope mapping phù hợp; khi dùng helper JWT giả lập, ta đang thử logic phân quyền, không xác minh token thật.

Ma trận chính xác bắt đầu từ quyết định nghiệp vụ đã thống nhất. Nếu không thống nhất “admin có vượt giới hạn tenant không?”, không có cơ sở chắc chắn để ghi kết quả `ALLOW` hay `DENY`.

## 4. Xây dựng danh mục danh tính và dữ liệu mẫu

Để số test có ý nghĩa, tạo **những danh tính khác nhau ở đúng điểm policy phân biệt**:

| Mã | Danh tính mẫu | Authentication | Quyền/thuộc tính |
|---|---|---|---|
| `I0` | Khách ẩn danh | Không có | Không có authorities |
| `I1` | `an` — khách hàng | Session | `ROLE_USER`; tenant `acme` |
| `I2` | `binh` — khách hàng | Session | `ROLE_USER`; tenant `acme` |
| `I3` | `chi` — khách hàng | Session | `ROLE_USER`; tenant `beta` |
| `I4` | `lan` — nhân viên báo cáo | Session | `ROLE_USER`, `REPORT_READ`; tenant `acme` |
| `I5` | `admin` — quản trị viên | Session | `ROLE_ADMIN`; quyền tenant theo policy đã chọn |
| `I6` | `partner-r` — đối tác | Bearer JWT | Scope `partner.read`, tenant `acme` |
| `I7` | `partner-w` — đối tác | Bearer JWT | Scope `partner.write`, **không có** `partner.read` |
| `I8` | Principal hết hạn/credential không hợp lệ | Credential lỗi | Không được xác thực thành công |

Tạo tài nguyên mẫu có khác biệt vừa đủ:

| Tài nguyên mẫu | Chủ sở hữu | Tenant | Trạng thái |
|---|---|---|---|
| Đơn `42` | `an` | `acme` | `DRAFT` |
| Đơn `43` | `binh` | `acme` | `DRAFT` |
| Đơn `44` | `an` | `acme` | `CLOSED` |
| Đơn `50` | `chi` | `beta` | `DRAFT` |

Những bản ghi này cố tình tạo ra hai ranh giới tách biệt:

- **Ownership:** `an` và `binh` cùng tenant nhưng chỉ một người là chủ đơn `42`.
- **Tenant:** `an` và `chi` ở hai tenant khác nhau dù đều có `ROLE_USER`.

Nếu chỉ tạo hai user thuộc hai tenant, một test trả `403` không cho biết hệ thống chặn nhờ ownership hay tenant. Nên tạo những cặp dữ liệu chỉ khác **một biến quan trọng**, để lý giải kết quả được.

Đặc biệt, tenant/owner trong ma trận phải phản ánh **nguồn dữ liệu tin cậy**. Test cần thử tình huống người dùng chỉnh `ownerId` hoặc `tenantId` trong request; hệ thống không được tin các trường đó để vượt quyền nếu chúng không được xác minh ở máy chủ.

## 5. Ma trận kiểm thử HTTP đủ chi tiết

Quy ước:

- `ALLOW` = xử lý request; `DENY` = từ chối truy cập.
- `C+` = CSRF token hợp lệ; `C−` = thiếu hoặc token không hợp lệ.
- Dấu `—` = điều kiện không liên quan đến tình huống này.
- Ký hiệu `I0`…`I8` và ID đơn lấy từ hai bảng trước.
- Dữ liệu đầu vào khác (payload, session, claim, profile) đều được tạo hợp lệ, trừ yếu tố mà dòng test đang chủ ý thay đổi.

### 5.1. Công khai, xác thực và quyền theo authority

| ID | Tài nguyên + action | Danh tính | Quyền / ngữ cảnh | Quyết định | HTTP mong đợi | Assertion bổ sung |
|---|---|---|---|---|---|---|
| `M01` | `GET /public/catalog` | `I0` | — | ALLOW | `200` | Chỉ dữ liệu công khai |
| `M02` | `GET /api/me` | `I0` | — | DENY | `401` | Không có dữ liệu tài khoản |
| `M03` | `GET /api/me` | `I1` | `ROLE_USER` | ALLOW | `200` | Trả dữ liệu của `an` |
| `M04` | `GET /api/reports` | `I0` | — | DENY | `401` | Không lộ báo cáo |
| `M05` | `GET /api/reports` | `I1` | Thiếu `REPORT_READ` | DENY | `403` | Không lộ báo cáo |
| `M06` | `GET /api/reports` | `I4` | Có `REPORT_READ` | ALLOW | `200` | Báo cáo trong phạm vi quyền |
| `M07` | `POST /api/reports` | `I4` | C+ nếu API yêu cầu CSRF | DENY | `403` | Không vô tình cho phép method khác |

`M07` giả định ứng dụng **từ chối method chưa công bố bằng security policy** trước khi xử lý controller. Nếu thiết kế ứng dụng để request đi qua security rồi controller trả `405 Method Not Allowed`, kỳ vọng phải được ghi là `405`; trường hợp này không thể dùng để thay thế kiểm thử phân quyền trên method thực sự được hỗ trợ.

Một ca quan trọng là `M05`: nếu rule bị thay sai từ `hasAuthority("REPORT_READ")` thành `authenticated()`, `M06` vẫn có thể xanh, nhưng `M05` phải thất bại.

### 5.2. Quyền theo tài nguyên, tenant và trạng thái

| ID | Tài nguyên + action | Chủ thể | Tình huống | Quyết định | HTTP mong đợi | Assertion bổ sung |
|---|---|---|---|---|---|---|
| `M08` | `GET /api/orders/42` | `I1` = `an` | Chủ đơn, cùng tenant | ALLOW | `200` | Đúng thông tin đơn `42` |
| `M09` | `GET /api/orders/42` | `I2` = `binh` | Cùng tenant, khác chủ | DENY | `403` | Không lộ dữ liệu đơn |
| `M10` | `GET /api/orders/50` | `I1` = `an` | Khác tenant, khác chủ | DENY | `403` | Không lộ dữ liệu tenant `beta` |
| `M11` | `GET /api/orders/42` | `I5` = `admin` | Có `ROLE_ADMIN` | ALLOW | `200` | Đúng dữ liệu và phạm vi admin |
| `M12` | `DELETE /api/orders/42` | `I2` = `binh` | Khác chủ; C+ | DENY | `403` | Đơn `42` vẫn tồn tại |
| `M13` | `DELETE /api/orders/42` | `I1` = `an` | Chủ đơn, `DRAFT`; C+ | ALLOW | `204` | Đơn `42` được xóa |
| `M14` | `DELETE /api/orders/44` | `I1` = `an` | Chủ đơn nhưng `CLOSED`; C+ | BUSINESS DENY | `409` | Đơn `44` không đổi |

`M14` chứng minh giới hạn trạng thái nghiệp vụ; `M12` chứng minh phân quyền. Hai loại từ chối khác nhau có thể cần cơ chế và HTTP status khác nhau. Nếu dự án chủ ý định nghĩa trạng thái là một phần của authorization policy thì `M14` có thể dùng `403`, nhưng phải thống nhất và test đúng thiết kế đó.

`M11` giả định role admin được truy cập đơn thuộc tenant được cấp quyền. Để kiểm chứng admin có vượt tenant hay không, phải bổ sung một dòng với `I5` truy cập đơn `50` và kỳ vọng theo policy thực tế.

### 5.3. CSRF, token, scope và xác thực thực

| ID | Tài nguyên + action | Danh tính | Điều kiện | Quyết định | HTTP mong đợi | Assertion bổ sung |
|---|---|---|---|---|---|---|
| `M15` | `POST /api/orders` | `I1` | C−; payload hợp lệ | DENY | `403` | Không tạo đơn |
| `M16` | `POST /api/orders` | `I1` | C+; payload hợp lệ | ALLOW | `201` | Chủ đơn mới là `an` |
| `M17` | `GET /partner/data` | `I0` | Không Bearer token | DENY | `401` | Có challenge phù hợp |
| `M18` | `GET /partner/data` | `I7` | Chỉ `partner.write` | DENY | `403` | Không lộ dữ liệu đối tác |
| `M19` | `GET /partner/data` | `I6` | `partner.read` và đúng tenant | ALLOW | `200` | Chỉ trả dữ liệu `acme` |
| `M20` | `GET /partner/data` | `I8` | JWT hết hạn/sai chữ ký/issuer | DENY | `401` | Decoder từ chối token |
| `M21` | `GET /partner/data` | `I6` | Scope đúng nhưng yêu cầu dữ liệu `beta` | DENY | `403` | Không truy xuất tenant khác |

**`M20` cần test qua decoder/validator thật.** Nếu dùng `jwt()` hoặc `mockJwt()` từ `spring-security-test`, test giả lập một `Authentication` hoặc JWT đã được chấp nhận và không kiểm chứng chữ ký, thời hạn hay issuer. Vì vậy không thể gán M20 cho một test chỉ dùng các helper ấy.

**`M15` và `M16` áp dụng cho nhánh dùng cookie/session có CSRF protection.** Với resource server thuần Bearer token được gửi tường minh bằng Authorization header, yêu cầu CSRF tùy vào cách ứng dụng sử dụng credentials và cấu hình security; không được tự động áp dụng quy tắc của session cho mọi API.

## 6. Từ ma trận đầy đủ sang tập ca kiểm thử gọn nhưng hiệu quả

Nếu có 8 principal × 5 tài nguyên × 4 HTTP method × 3 trạng thái × 2 trạng thái CSRF, phép nhân cơ học tạo ra 960 tổ hợp. Nhiều tổ hợp vô nghĩa: `GET` công khai không cần CSRF, JWT scope không liên quan trực tiếp đến controller chỉ dùng session, hoặc một endpoint không hỗ trợ `DELETE`.

Lập ma trận theo ba bước:

1. **Liệt kê route và quy tắc thật:** tài nguyên, action được hỗ trợ, cơ chế xác thực, quyền cần có, dữ liệu liên quan.
2. **Phân hoạch các giá trị tương đương:** ví dụ quyền đủ/thiếu; cùng chủ/khác chủ; cùng tenant/khác tenant; CSRF hợp lệ/thiếu. Nếu hai principal cùng kích hoạt đúng một nhánh policy, có thể chọn một đại diện.
3. **Thêm ranh giới có rủi ro cao:** path ID khác owner, cùng role nhưng khác tenant, HTTP method không công bố, order trạng thái đóng, JWT sai issuer, claim bị giả mạo.

Để mỗi rule có bằng chứng đủ mạnh, tối thiểu nên cân nhắc:

- Một **ca cho phép** với toàn bộ điều kiện hợp lệ.
- Một **ca thiếu xác thực** nếu endpoint yêu cầu danh tính.
- Một **ca đã xác thực nhưng thiếu quyền**.
- Một **ca thay đổi thuộc tính tài nguyên** như owner hoặc tenant trong khi giữ danh tính và quyền như cũ.
- Một **ca sai điều kiện HTTP/ngữ cảnh**, ví dụ CSRF thiếu trên thao tác ghi.
- Một **ca đã bị từ chối nhưng không tạo side effect** nếu request thay đổi trạng thái.

Không cần thực hiện mọi dòng ở mọi tầng test. Với những tổ hợp lớn, dùng **pairwise/covering array** như kỹ thuật giảm số ca sau khi đã giữ lại các ca trọng yếu; không được để thuật toán giảm tổ hợp loại mất trường hợp từ chối có rủi ro cao.

Một quy tắc bao phủ có ích hơn tỷ lệ test code là: **Nếu thay đổi matcher từ quyền hẹp sang `authenticated()`, test nào sẽ đỏ?** Nếu không có câu trả lời, vẫn thiếu ca negative cho phép quá rộng.

## 7. Chuyển từng dòng thành một đặc tả test

Mỗi dòng ma trận phải mô tả đủ đầu vào và bằng chứng:

```text
CASE M12
  Resource:         order 42, owner=an, tenant=acme, status=DRAFT
  Action:           DELETE /api/orders/42
  Authentication:   session user=binh
  Authorities:      [ROLE_USER]
  Context:          binh.tenant=acme, CSRF=valid
  Expected:         HTTP 403
  Data assertion:   order 42 still exists, unchanged
  Control assertion: no order-deleted domain event emitted
```

Tên test có thể phản ánh trực tiếp chính sách:

```text
M12_otherOwnerCannotDeleteEvenWithValidCsrf
M13_ownerCanDeleteDraftOrderWithValidCsrf
M14_ownerCannotDeleteClosedOrder
M18_partnerWithoutReadScopeCannotRead
```

Tại sao cần thêm “CSRF hợp lệ” trong `M12`? Vì nếu thiếu CSRF, filter có thể trả `403` trước khi ownership rule được gọi. Khi đó test xanh dù rule ownership đã bị gỡ. Để chứng minh phân quyền, hãy làm **tất cả điều kiện khác đều hợp lệ**, chỉ thay yếu tố quyền muốn kiểm tra.

Với kiểm thử từ chối, không chỉ kiểm tra status. Chẳng hạn:

- `M09`: kiểm tra body không chứa địa chỉ giao hàng hoặc số điện thoại của `an`.
- `M12`: xác nhận đơn `42` còn tồn tại, trường trạng thái không đổi, không phát sự kiện xóa.
- `M21`: xác nhận không trả dữ liệu của tenant `beta` ngay cả khi token có scope đọc hợp lệ.

## 8. Dữ liệu hóa ma trận thành kiểm thử Servlet với MockMvc

`MockMvc` giúp đưa các dòng ma trận thành request Servlet. Ví dụ dưới đây giả định ứng dụng có endpoint `GET /api/reports` với `SecurityFilterChain` yêu cầu `REPORT_READ`, cấu hình API trả `401` khi chưa xác thực và controller trả `200` khi được phép.

Để kiểm tra filter chain thật của ứng dụng, có thể dùng `@SpringBootTest` + `@AutoConfigureMockMvc` (hoặc `@WebMvcTest` + cấu hình security được nạp đúng, nếu muốn kiểm thử theo lát cắt).

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAccessMatrixTest {

    @Autowired MockMvc mvc;

    static Stream<Arguments> authenticatedCases() {
        return Stream.of(
            Arguments.of(
                "M05",
                "an",
                List.of("ROLE_USER"),
                403
            ),
            Arguments.of(
                "M06",
                "lan",
                List.of("ROLE_USER", "REPORT_READ"),
                200
            )
        );
    }

    @ParameterizedTest(name = "{0}: expected HTTP {3}")
    @MethodSource("authenticatedCases")
    void reportAccessFollowsAuthorityMatrix(
            String caseId,
            String username,
            List<String> authorityNames,
            int expectedStatus) throws Exception {

        GrantedAuthority[] granted = authorityNames.stream()
            .map(SimpleGrantedAuthority::new)
            .toArray(GrantedAuthority[]::new);

        mvc.perform(get("/api/reports")
                .with(user(username).authorities(granted)))
            .andExpect(status().is(expectedStatus));
    }

    @Test
    void m04_anonymousCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }
}
```

Những `import` Java được lược bỏ: các hàm `get()`, `user()` và `status()` thuộc thư viện test tương ứng; `Arguments`, `ParameterizedTest`, `MethodSource` thuộc JUnit Jupiter; `SimpleGrantedAuthority` và `GrantedAuthority` thuộc Spring Security. `caseId` giúp kết quả báo lỗi liên kết ngược đến dòng ma trận; trong một project cụ thể nên đưa ID vào tên test/log khi runner hiển thị.

Cách sinh `GrantedAuthority[]` từ danh sách chính xác tránh nhầm giữa role và authority. Nếu code dùng `hasRole("ADMIN")`, hàng tương ứng cần có `ROLE_ADMIN`, không phải `ADMIN`.

**Kiểm tra độ tin cậy của ca test:** nếu controller thật không tồn tại hoặc trả `404`, ca `M06` phải đỏ. Nếu `MockMvc` đang được cấu hình `addFilters = false`, ca `M05` không thể chứng minh filter chain. Nếu service được mock trong `@WebMvcTest`, không suy luận rằng permission ở service thật đã chạy.

### Hàng kiểm thử CSRF cho POST/DELETE

Đối với nhánh dùng session có CSRF, Servlet cung cấp `csrf()` trong `SecurityMockMvcRequestPostProcessors`:

```java
mvc.perform(post("/api/orders")
        .with(user("an").roles("USER"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\"SKU-1\",\"quantity\":1}"))
    .andExpect(status().isForbidden());

mvc.perform(post("/api/orders")
        .with(user("an").roles("USER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\"SKU-1\",\"quantity\":1}"))
    .andExpect(status().isCreated());
```

Các ví dụ giả định endpoint và dữ liệu hợp lệ, người dùng có quyền tạo đơn và CSRF đang bật cho nhánh này. Để chứng minh `M15`/`M16` đầy đủ, test nên kiểm tra số đơn trước/sau, chủ sở hữu đơn mới hoặc repository nếu cần.

### Hàng kiểm thử owner và tenant

Test `M12` có thể thực hiện theo cấu trúc dưới đây. Bản ghi `42` với owner `an` và trạng thái `DRAFT` phải được seed trong fixture; test nhận diện đúng dữ liệu đã tạo.

```java
@Test
void m12_otherOwnerCannotDeleteEvenWithValidCsrf() throws Exception {
    // Fixture: order 42 owner=an, tenant=acme, status=DRAFT.
    mvc.perform(delete("/api/orders/{id}", 42L)
            .with(user("binh").roles("USER"))
            .with(csrf()))
        .andExpect(status().isForbidden());

    assertThat(orderRepository.existsById(42L)).isTrue();
}
```

Đây là **mảnh ví dụ tích hợp**: `orderRepository` và fixture phải tồn tại trong project; ví dụ chỉ thể hiện cách dựng request và assertion. Cũng cần kiểm tra các trường quan trọng không đổi nếu request có thể thay đổi một phần dữ liệu trước khi bị từ chối. Với một test service được bọc transaction, cần lưu ý thời điểm flush/commit để assertion về DB đáng tin cậy.

**Đừng** cho client gửi `ownerId = "an"` rồi dùng trực tiếp trường đó để giả lập “là chủ sở hữu”. Chủ thể của request phải đến từ `Authentication` tin cậy; owner thật lấy từ tài nguyên đã lưu.

## 9. Chuyển ma trận sang WebTestClient trong Reactive

Ứng dụng WebFlux dùng `SecurityWebFilterChain` và Reactor security context. Với `WebTestClient` bind vào application context, có thể áp dụng `springSecurity()` để thêm security test support:

```java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class ReactiveReportMatrixTest {

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void m05_missingReportAuthorityIsForbidden() {
        client.mutateWith(mockUser("an")
                .authorities(new SimpleGrantedAuthority("ROLE_USER")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void m06_reportReaderIsAllowed() {
        client.mutateWith(mockUser("lan")
                .authorities(
                    new SimpleGrantedAuthority("REPORT_READ")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk();
    }
}
```

`springSecurity()` và `mockUser()` ở đây là các API của `SecurityMockServerConfigurers` và `SecurityMockServerRequestPostProcessors`. Để kiểm tra request CSRF trong Reactive, dùng `mutateWith(csrf())`; để giả lập JWT, dùng `mutateWith(mockJwt())`.

Cùng một ý tưởng ma trận áp dụng cho cả Servlet và Reactive, nhưng các helper xây dựng request khác nhau. Kiểm tra rằng mã test sử dụng đúng bộ helper cho stack, và app đang nạp chain/filter tương ứng.

Nếu `WebTestClient` được bind **đến một server qua mạng** bằng `bindToServer()`, đừng dùng mock authentication trong client như thể nó thay cho credential HTTP thật. Khi đó cần gửi Authorization header hoặc cookie/token thực để chứng minh đường đi qua authentication mechanism.

## 10. JWT/OAuth2/OIDC: thêm claims, scope và loại danh tính vào ma trận

Với token-based security, danh tính không thể được mô tả bằng mỗi username. Có thể cần các trường:

| Trường | Ví dụ | Mục đích trong policy |
|---|---|---|
| `sub` | `partner-r` | Định danh principal |
| `iss` | `https://idp.example.test` | Token phải đến từ issuer được tin cậy |
| `aud` | `orders-api` | Token được phát hành cho API phù hợp |
| `exp` | Timestamp tương lai | Token còn hạn |
| `scope`/`scp` | `partner.read` | Cấp quyền đọc |
| `tenant_id` | `acme` | Giới hạn dữ liệu theo tenant |
| Loại authentication | Bearer JWT, OAuth2 login, OIDC login | Xác định nhánh security áp dụng |

Có hai **nhóm ca kiểm thử phải tách rõ**:

**Nhóm A — Authorization theo identity/claims đã được chấp nhận.** Dùng JWT/OAuth2/OIDC giả lập để thay scope, principal, claim, authorities và xem policy cho phép hoặc từ chối. Trên Servlet dùng `jwt()`, `oauth2Login()`, `oidcLogin()`; trên Reactive dùng `mockJwt()`, `mockOAuth2Login()`, `mockOidcLogin()`. Các helper này cung cấp authentication giả lập; chúng không chạy đầy đủ quá trình cấp token/đăng nhập thật.

**Nhóm B — Authentication/validation thực.** Gửi token thật, đã ký sai, hết hạn, có issuer/audience không hợp lệ hoặc không có token qua HTTP vào decoder/validator thực và kiểm tra bị từ chối. Cần fixture và cấu hình của resource server phù hợp; không thể dùng helper nhóm A để chứng minh nhóm B.

Ví dụ kiểm chứng dòng `M18`/`M19` trên Servlet, giả định token scope được ánh xạ thành authority `SCOPE_partner.read`:

```java
mvc.perform(get("/partner/data")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_partner.write"))))
    .andExpect(status().isForbidden());

mvc.perform(get("/partner/data")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_partner.read"))))
    .andExpect(status().isOk());
```

Reactive tương ứng:

```java
client.mutateWith(mockJwt()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_partner.read")))
    .get().uri("/partner/data")
    .exchange()
    .expectStatus().isOk();
```

Muốn chứng minh claim `tenant_id` được ánh xạ đúng thành nguyên tắc truy cập tài nguyên, cần dựng claim theo converter và policy thực của ứng dụng, hoặc test trực tiếp converter nếu đó là trách nhiệm của ứng dụng. Gắn mỗi authority thủ công bằng `jwt().authorities(...)` **bỏ qua bài toán mapping** từ claim sang authority.

Đối với OAuth2 login và OIDC login, ngoài scope cần kiểm tra những claim/attribute mà app thực sự dựa vào, ví dụ mã người dùng nội bộ hoặc nhóm được cấp quyền. Nếu một rule dựa trên OIDC `preferred_username` hay `groups`, đừng mặc định principal giả chỉ có `username`/`ROLE_USER` là đủ.

## 11. Kiểm tra ma trận ở nhiều lớp bảo vệ

Một hệ thống có thể có ít nhất ba điểm quyết định:

| Lớp | Chức năng | Test nên chứng minh |
|---|---|---|
| Request security | `SecurityFilterChain` / `SecurityWebFilterChain` | Method và route có yêu cầu xác thực/authority đúng |
| Method security | `@PreAuthorize` / `@PostAuthorize`; Reactive tương ứng | Quy tắc tại service thực thi qua Spring-managed bean/proxy |
| Business/data authorization | Kiểm tra owner, tenant, trạng thái bản ghi | Không đọc/ghi tài nguyên khác chủ, không vượt tenant |

Ví dụ, security chain có thể cho phép mọi user đã đăng nhập gọi `DELETE /api/orders/{id}`, sau đó service mới thực thi rule ownership. Trong trường hợp ấy, một test slice chỉ mock service không chứng minh ownership. Cần integration test qua service và repository thật (hoặc unit test policy cộng kiểm tra tích hợp về wiring).

Một yêu cầu `DELETE` bị từ chối phải xác minh **kết quả ở tầng dữ liệu**. Trạng thái `403` có thể đúng nhưng không đủ nếu thay đổi đã được ghi trước khi xuất hiện lỗi, hoặc event đã được phát ra ngoài hệ thống.

Với WebFlux, bảo mật theo phương thức thường dựa trên reactive context. Khi mã dùng `Mono`/`Flux`, chú ý chủ thể được truyền trong Reactor context tương ứng; một test unit đặt `SecurityContextHolder` kiểu ThreadLocal không bảo đảm có cùng ngữ nghĩa trong pipeline Reactive.

## 12. Giữ ma trận đồng bộ với code và tránh trùng lặp

Ma trận sẽ mất giá trị nếu chỉ nằm trong một tài liệu và không được cập nhật khi thêm endpoint hoặc đổi quyền. Có thể lưu một bản hợp đồng ở dạng dữ liệu để test runner đọc và chạy; ví dụ biểu diễn rút gọn:

```yaml
cases:
  - id: M05
    method: GET
    path: /api/reports
    principal: an
    authorities: [ROLE_USER]
    expectedStatus: 403

  - id: M06
    method: GET
    path: /api/reports
    principal: lan
    authorities: [ROLE_USER, REPORT_READ]
    expectedStatus: 200

  - id: M18
    method: GET
    path: /partner/data
    authentication: mock-jwt
    authorities: [SCOPE_partner.write]
    expectedStatus: 403
```

Ví dụ chỉ là **định dạng minh họa để quản lý test cases**, không phải cấu hình Spring Security. Khi phát triển thật, viết bộ chuyển đổi từ dữ liệu sang request và cần xử lý các thuộc tính như owner, tenant, token, CSRF và side effects rõ ràng.

Một số quy tắc duy trì ma trận:

- **Mỗi dòng có ID ổn định** để tra ngược từ test failure về policy.
- **Không gộp bản chất lỗi khác nhau**: `401` do thiếu xác thực, `403` do thiếu quyền, `409` do trạng thái nghiệp vụ cần phân biệt.
- **Không tạo test trùng chỉ thay tên người dùng** nếu hai người cùng nhánh điều kiện, trừ khi username/tenant là biến cần kiểm tra.
- **Bắt buộc có ca từ chối đã xác thực** ở endpoint cần authority, để phát hiện vô tình mở rộng quyền.
- **Cập nhật các đối tượng mẫu** khi thêm field owner/tenant mới; test cũ dùng dữ liệu thiếu field có thể phát hiện lỗi sai nguyên nhân.
- **Kiểm tra thay đổi của matcher và order** nếu có nhiều security filter chain; một đường dẫn có thể đi nhầm chain khi matcher rộng được ưu tiên.

Đối với định lượng, tránh kết luận “bao phủ 100%” chỉ vì mọi endpoint có ít nhất một test. Độ bao phủ policy có ý nghĩa hơn nếu mỗi rule có **ca cho phép + ca từ chối + trường hợp biên quan trọng**.

## 13. Một ví dụ xây ma trận từ đầu đến cuối

Yêu cầu mới:

> Chỉ chủ hóa đơn có `INVOICE_READ` hoặc người hỗ trợ có `ROLE_SUPPORT` đúng tenant mới được xem hóa đơn. Chỉ nhân viên có `INVOICE_REFUND` và cùng tenant mới được hoàn tiền hóa đơn ở trạng thái `PAID`; thao tác refund từ web yêu cầu CSRF hợp lệ.

**Bước 1: Chọn tài nguyên và hành động.** `GET /api/invoices/{id}` và `POST /api/invoices/{id}/refund`.

**Bước 2: Tạo danh tính đại diện.** Anonymous; owner cùng tenant có `INVOICE_READ`; owner thiếu authority; support cùng tenant; support khác tenant; refund staff có `INVOICE_REFUND`; refund staff thiếu quyền.

**Bước 3: Tạo fixture.** Invoice `101` chủ `an`, tenant `acme`, trạng thái `PAID`; invoice `102` cùng tenant nhưng chủ `binh`; invoice `201` thuộc tenant `beta`; invoice `103` thuộc `acme` nhưng `REFUNDED`.

**Bước 4: Ghi các dòng bắt buộc.**

| ID | Case | Kết quả mong đợi |
|---|---|---|
| `I01` | Ẩn danh đọc `101` | `401`, không có dữ liệu |
| `I02` | `an` + `INVOICE_READ` đọc `101` | `200`, đúng invoice |
| `I03` | `an` thiếu `INVOICE_READ` đọc `101` | `403` |
| `I04` | `binh` + `INVOICE_READ` đọc `101` | `403` vì khác chủ |
| `I05` | Support cùng tenant đọc `101` | `200` theo policy |
| `I06` | Support khác tenant đọc `101` | `403` |
| `I07` | Refund staff đủ quyền, đúng tenant, invoice `PAID`, C+ | Được refund, dữ liệu thay đổi chính xác |
| `I08` | Refund staff thiếu `INVOICE_REFUND`, C+ | `403`, invoice không đổi |
| `I09` | Refund staff đủ quyền, khác tenant, C+ | `403`, invoice không đổi |
| `I10` | Refund staff đủ quyền, cùng tenant, thiếu CSRF | `403`, invoice không đổi |
| `I11` | Refund staff đủ quyền, cùng tenant, invoice đã `REFUNDED`, C+ | Lỗi trạng thái theo hợp đồng, không refund lần hai |

**Bước 5: Phân bổ test hợp lý.** Kiểm tra rule owner/tenant và trạng thái bằng unit tests; kiểm tra HTTP matcher, authenticated/anonymous, authority và CSRF bằng `MockMvc` hoặc `WebTestClient`; kiểm tra repository và tác động refund bằng integration tests; dùng một hành trình HTTP/browser có session thật nếu sản phẩm yêu cầu xác minh cookie, CSRF token và đăng nhập end-to-end.

**Bước 6: Thử tác động của một lỗi cố ý trong suy nghĩ.** Nếu bỏ điều kiện cùng tenant, `I06`/`I09` phải thất bại. Nếu đổi `hasAuthority("INVOICE_READ")` thành `authenticated()`, `I03` phải thất bại. Nếu bỏ CSRF, `I10` phải thất bại. Nếu bỏ kiểm tra trạng thái, `I11` phải thất bại. Đó là cách đánh giá chất lượng ma trận thông qua lỗi mà test có thể phát hiện.

## 14. Bài tập thực hành và tiêu chí hoàn thành

**Bài tập:** Ứng dụng Spring Security cung cấp:

- `GET /api/documents/{id}`: chủ tài liệu có `DOCUMENT_READ` được xem; quản trị viên có `ROLE_ADMIN` và đúng tenant được xem.
- `PATCH /api/documents/{id}`: chủ tài liệu có `DOCUMENT_EDIT` được sửa nếu tài liệu ở trạng thái `DRAFT`; request từ session cần CSRF.
- `GET /partner/documents`: đối tác Bearer JWT cần scope `documents.read` và chỉ được xem tenant tương ứng.

Hãy xây ma trận ít nhất **12 dòng**, trong đó có: anonymous, authenticated thiếu quyền, cùng chủ/khác chủ, cùng tenant/khác tenant, đúng/sai trạng thái, CSRF thiếu/hợp lệ, JWT thiếu scope, JWT scope đúng nhưng tenant sai, token thật hết hạn. Mỗi dòng phải chỉ rõ HTTP status theo hợp đồng hệ thống, dữ liệu cần quan sát và tầng test phù hợp.

Sau đó viết một test data-driven dùng `MockMvc` hoặc `WebTestClient` cho cặp “có/thiếu `DOCUMENT_READ`” và một integration test chứng minh yêu cầu sửa tài liệu bị từ chối không làm thay đổi database. Với ca token hết hạn, ghi rõ cách để decoder thật xử lý token thay vì chỉ tạo authentication giả.

**Tiêu chí tự kiểm:** Ma trận đã trả lời rõ sáu câu hỏi: tài nguyên nào, hành động gì, danh tính nào, quyền gì, điều kiện nào và kết quả quan sát nào? Nếu một rule quyền bị nới lỏng, test nào sẽ đỏ? Nếu rule ownership/tenant bị bỏ, test nào sẽ đỏ? Nếu CSRF bị tắt hoặc JWT decoder cấu hình sai, bài test nào phát hiện?

Một ma trận tốt là **bản đặc tả kiểm chứng được** của chính sách bảo mật. Nó kết nối yêu cầu nghiệp vụ với các ca kiểm thử cho phép, bị từ chối và trường hợp biên, dù hệ thống chạy trên Servlet với `MockMvc` hay Reactive với `WebTestClient`.
