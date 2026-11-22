# Test truy cập object của user hoặc tenant khác

Object authorization chỉ đáng tin khi được kiểm chứng bằng những request thực tế của nhiều chủ thể khác nhau. Một endpoint có thể hoạt động đúng với người sở hữu dữ liệu nhưng vẫn để người dùng khác đọc, sửa, xóa hoặc kích hoạt hành động trên cùng object. Trong hệ thống multi-tenant, lỗi còn có thể làm dữ liệu vượt qua ranh giới giữa các tổ chức.

Kiểm thử truy cập chéo (*cross-user* và *cross-tenant authorization testing*) tạo ra nhiều principal, object và quan hệ quyền khác nhau, sau đó xác minh server chỉ cho phép đúng các tổ hợp actor/action/object đã được chính sách phê duyệt. Bài kiểm thử phải quan sát cả response lẫn trạng thái dữ liệu và side effect. Một response `403` hoặc `404` không chứng minh hệ thống an toàn nếu database, message hoặc dịch vụ phụ thuộc vẫn bị thay đổi.

## 1. Phân biệt lỗi truy cập chéo user và tenant

Hai nhóm lỗi có liên quan nhưng cần fixture và test riêng:

- **Cross-user / BOLA:** người dùng A truy cập object thuộc người dùng B trong cùng tenant hoặc cùng hệ thống. Ví dụ A đọc hóa đơn của B bằng cách thay `invoiceId`.
- **Cross-tenant isolation failure:** người dùng thuộc tenant A truy cập dữ liệu của tenant B. Ví dụ caller sửa `tenantId`, đổi public ID hoặc gọi endpoint tìm kiếm với bộ lọc tenant khác.

Kiểm tra tenant isolation không thay thế kiểm tra owner. Hai người dùng trong cùng một tenant có thể không được quyền đọc dữ liệu riêng của nhau. Ngược lại, một nhân viên được ủy quyền có thể được truy cập object của nhiều người trong cùng tenant nhưng không được vượt sang tenant khác.

Mỗi test cần xác định rõ chính sách mong muốn. Không giả định mọi object chỉ thuộc một người hoặc mọi admin đều có quyền trên tất cả tenant.

## 2. Xây dựng bộ dữ liệu kiểm thử có chủ đích

Hãy tạo các principal và object đủ để phân biệt quyền sở hữu, vai trò, tenant và quan hệ ủy quyền. Một bộ fixture cơ bản có thể gồm:

| Chủ thể | Tenant | Vai trò/quan hệ | Dữ liệu sở hữu hoặc được cấp quyền |
|---|---|---|---|
| Alice | `tenant-A` | Customer | Invoice A1 và Order A1 |
| Bob | `tenant-A` | Customer | Invoice B1 và Order B1 |
| Carol | `tenant-B` | Customer | Invoice C1 và Order C1 |
| Support A | `tenant-A` | Support agent | Được giao xử lý một số object trong tenant A |
| Service X | `tenant-A` | Service account | Chỉ có quyền gọi thao tác nội bộ được quy định |
| Anonymous | Không có | Chưa xác thực | Không có principal |

Bộ dữ liệu này tạo ra ít nhất ba trường hợp cần phân biệt: Alice truy cập object của chính mình, Alice truy cập object của Bob trong cùng tenant, và Alice truy cập object của Carol ở tenant khác. Thêm trường hợp support agent được ủy quyền để tránh viết policy quá đơn giản chỉ dựa trên owner.

Fixture nên được tạo với ID ngẫu nhiên hoặc được lưu trong biến test. Không dựa vào ID tăng dần như `1001`, `1002` để giả định object nào thuộc ai. Nếu test cần mô phỏng enumeration, hãy lấy ID thực tế của fixture Bob rồi gửi bằng principal Alice; điều này kiểm tra authorization ngay cả khi ID đã bị lộ.

Dữ liệu test cần độc lập và có thể tái tạo. Dùng tenant, email và mã tham chiếu giả lập; không sao chép dữ liệu production hoặc thông tin cá nhân thật. Mỗi test nên tự tạo hoặc reset fixture để thứ tự chạy không làm thay đổi kết quả.

## 3. Lập ma trận actor, action và object trước khi viết test

Ma trận quyền là cơ sở để xác định test nào phải pass và test nào phải bị từ chối. Ví dụ với API hóa đơn:

| Actor | Object | Action | Kết quả mong đợi |
|---|---|---|---|
| Alice | Invoice A1 | Read | Allow |
| Alice | Invoice A1 | Update địa chỉ nhận hóa đơn | Allow nếu trạng thái cho phép |
| Alice | Invoice B1 | Read | Deny |
| Alice | Invoice B1 | Update/Delete | Deny, không có side effect |
| Alice | Invoice C1 | Read/Update | Deny do khác tenant |
| Bob | Invoice B1 | Read | Allow |
| Support A | Invoice B1 | Read | Allow nếu có grant còn hiệu lực |
| Support A | Invoice B1 | Refund | Deny nếu grant chỉ cấp quyền đọc |
| Service X | Invoice A1 | Internal operation | Chỉ allow action được cấp cho service |
| Anonymous | Invoice A1 | Read | Deny do chưa xác thực |

Hãy lập ma trận riêng cho từng nhóm endpoint và từng loại object. Một scope như `invoices:read` có thể cho phép gọi chức năng đọc, nhưng không tự động cho phép đọc mọi hóa đơn. Test cần kiểm tra cả quyền chức năng và quyền trên object.

## 4. Bao phủ toàn bộ đường truy cập tới object

Không chỉ kiểm tra endpoint lấy chi tiết theo ID. Cùng một object có thể được truy cập qua nhiều API và luồng khác nhau:

| Đường truy cập | Ví dụ | Điều cần xác minh |
|---|---|---|
| Chi tiết | `GET /api/invoices/{id}` | Caller không đọc được object của user/tenant khác |
| Cập nhật | `PUT` hoặc `PATCH /api/invoices/{id}` | Không thay đổi object ngoài quyền hoặc trường nội bộ |
| Xóa/hủy | `DELETE /api/invoices/{id}` | Không xóa hoặc phát sinh hành động trên object khác |
| Danh sách | `GET /api/invoices` | Chỉ trả object trong phạm vi caller; `total` cũng đúng phạm vi |
| Tìm kiếm/lọc | `GET /api/invoices?customerId=...` | Bộ lọc do client gửi không mở rộng quyền |
| Tài nguyên con | `/api/orders/{orderId}/items/{itemId}` | Item phải thuộc order được chỉ định và caller có quyền trên order |
| Tệp | `/api/invoices/{id}/pdf` | Kiểm tra quyền trên cả invoice và file liên quan |
| Bulk | `POST /api/invoices/bulk-export` | Kiểm tra từng ID và xử lý partial/all-or-nothing đúng hợp đồng |
| Thao tác nghiệp vụ | `/api/orders/{id}/cancel` | Quyền object và trạng thái nghiệp vụ đều được kiểm tra |
| Tác vụ bất đồng bộ | Export job hoặc message queue | Job không mang quyền vượt quá actor/service được phép |

Với mỗi đường truy cập, thay ID bằng ID thật của object khác. Kiểm tra cả ID ở path, query, body, header và trường tham chiếu lồng nhau. Nếu server dùng một ID từ body để truy vấn object, test phải thử thay trường đó dù path không thay đổi.

## 5. Kiểm tra cả quyền đọc và quyền ghi

Một số ứng dụng chỉ test `GET` nên bỏ sót lỗi nghiêm trọng ở `PUT`, `PATCH`, `DELETE` hoặc endpoint thực hiện giao dịch. Với object của Bob, Alice cần bị từ chối ở tất cả thao tác mà policy không cấp.

Đối với request ghi, ngoài response, hãy xác minh:

- Giá trị trong database không thay đổi.
- `updatedAt`, `updatedBy`, version hoặc audit record không bị cập nhật sai.
- Không có event, message, notification hoặc job được tạo.
- Không có lời gọi downstream như thanh toán, hoàn tiền, gửi email hoặc xóa file.
- Không có object con nào bị thay đổi qua cascade hoặc mapping tự động.

Ví dụ, nếu Alice gửi request hủy Order B1 và nhận `404`, test vẫn phải xác nhận trạng thái Order B1 không đổi và Payment Service không nhận yêu cầu hoàn tiền. Đây là cách phát hiện lỗi kiểm tra quyền được thực hiện sau side effect.

Với các thao tác có trạng thái, cần test cả trạng thái cho phép và trạng thái cấm. Người sở hữu đơn hàng cũng không được hủy đơn đã giao nếu quy tắc nghiệp vụ không cho phép.

## 6. Ví dụ kiểm thử tích hợp với Spring Security và MockMvc

Ví dụ dưới đây minh họa cách gửi request với JWT có subject và authority khác nhau. Cần có `spring-security-test` trong test scope và cấu hình Resource Server/Spring Security của ứng dụng.

```java
@SpringBootTest
@AutoConfigureMockMvc
class InvoiceAuthorizationIT {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    InvoiceRepository invoiceRepository;

    @Autowired
    AuthorizationTestData testData;

    @Test
    void ownerCanReadOwnInvoice() throws Exception {
        TestInvoice invoice = testData.createInvoice(
                "alice", "tenant-A");

        mockMvc.perform(get("/api/invoices/{id}", invoice.publicId())
                        .with(jwt().jwt(token -> token
                                .subject("alice")
                                .claim("tenant_id", "tenant-A"))
                                .authorities(new SimpleGrantedAuthority(
                                        "SCOPE_invoices:read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id")
                        .value(invoice.publicId().toString()));
    }

    @Test
    void userCannotReadAnotherUsersInvoiceInSameTenant()
            throws Exception {
        TestInvoice bobsInvoice = testData.createInvoice(
                "bob", "tenant-A");

        mockMvc.perform(get("/api/invoices/{id}", bobsInvoice.publicId())
                        .with(jwt().jwt(token -> token
                                .subject("alice")
                                .claim("tenant_id", "tenant-A"))
                                .authorities(new SimpleGrantedAuthority(
                                        "SCOPE_invoices:read"))))
                .andExpect(status().isNotFound());
    }

    @Test
    void userCannotReadInvoiceFromAnotherTenant() throws Exception {
        TestInvoice carolsInvoice = testData.createInvoice(
                "carol", "tenant-B");

        mockMvc.perform(get("/api/invoices/{id}", carolsInvoice.publicId())
                        .with(jwt().jwt(token -> token
                                .subject("alice")
                                .claim("tenant_id", "tenant-A"))
                                .authorities(new SimpleGrantedAuthority(
                                        "SCOPE_invoices:read"))))
                .andExpect(status().isNotFound());
    }
}
```

Đây là ví dụ khung; `AuthorizationTestData`, kiểu `TestInvoice`, repository và response cần thay bằng fixture của ứng dụng. Nếu policy dùng `403` thay vì `404`, điều chỉnh assertion theo hợp đồng. JWT request postprocessor thường tạo principal đã xác thực cho test MVC; nó không kiểm tra chữ ký JWT thực tế, vì vậy cần một nhóm test riêng cho cấu hình decoder, issuer, audience và expiry.

Điều quan trọng là test thứ hai và thứ ba dùng principal Alice nhưng ID của Bob/Carol. Nếu chỉ kiểm tra token hợp lệ hoặc authority `invoices:read`, test chưa chứng minh object authorization hoạt động.

## 7. Xác minh dữ liệu không thay đổi sau request bị từ chối

Với thao tác ghi, hãy kiểm tra trạng thái trước và sau. Ví dụ:

```java
@Test
void userCannotUpdateAnotherUsersInvoice() throws Exception {
    TestInvoice invoice = testData.createInvoice("bob", "tenant-A");
    String originalAddress = invoiceRepository
            .findByPublicId(invoice.publicId())
            .orElseThrow()
            .getBillingAddress();

    mockMvc.perform(patch("/api/invoices/{id}", invoice.publicId())
                    .with(jwt().jwt(token -> token
                            .subject("alice")
                            .claim("tenant_id", "tenant-A"))
                            .authorities(new SimpleGrantedAuthority(
                                    "SCOPE_invoices:write")))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"billingAddress":"attacker-controlled"}
                            """))
            .andExpect(status().isNotFound());

    Invoice persisted = invoiceRepository
            .findByPublicId(invoice.publicId())
            .orElseThrow();
    assertThat(persisted.getBillingAddress()).isEqualTo(originalAddress);
}
```

Trong hệ thống có audit, event hoặc downstream integration, bổ sung assertion cho các thành phần đó. Nếu test dùng transaction rollback để dọn fixture, cần bảo đảm cách chạy request và transaction không làm assertion đọc nhầm persistence context cũ; có thể flush/clear entity manager hoặc đọc lại qua repository trong transaction mới tùy cấu hình test.

## 8. Kiểm tra tenant context và dữ liệu client tự khai

Một lỗi thường gặp là server lấy `tenantId` từ body hoặc query thay vì từ security context. Tạo test trong đó Alice thuộc tenant A gửi:

```json
{
  "tenantId": "tenant-B",
  "ownerId": "carol",
  "name": "Changed by Alice"
}
```

Các kết quả cần xác minh:

- Server không dùng tenant hoặc owner do client khai để mở rộng phạm vi.
- Trường ngoài DTO bị từ chối hoặc bỏ qua theo contract.
- Object của Carol không bị cập nhật.
- Object của Alice cũng không bị chuyển sang tenant B ngoài ý muốn.
- Log/audit không ghi nhận Alice như người có quyền của tenant B.

Ngoài việc thay claim `tenant_id`, hãy kiểm tra claim không hợp lệ, thiếu tenant, tenant đã bị thu hồi và principal có quyền nhiều tenant. Với principal được cấp quyền nhiều tenant, test cần xác minh caller chỉ thao tác trên tenant được chọn trong security context và policy tương ứng.

## 9. Kiểm thử list, search, pagination và aggregate

Endpoint danh sách có thể không nhận object ID trực tiếp nhưng vẫn làm lộ dữ liệu ngoài phạm vi. Tạo dữ liệu của Alice, Bob và Carol rồi kiểm tra:

- Kết quả chỉ chứa object được phép truy cập.
- `totalElements`, `totalCount`, facet, thống kê và aggregate chỉ tính trong phạm vi caller.
- Bộ lọc `ownerId`, `tenantId`, `customerId` không cho phép caller xem dữ liệu ngoài quyền.
- Sort, cursor và page token không làm lộ ID hoặc dữ liệu của tenant khác.
- Tìm kiếm theo prefix, email, số hóa đơn hoặc khoảng thời gian không thể dò object ngoài phạm vi.
- Export tạo từ cùng bộ lọc cũng áp dụng cùng authorization như list endpoint.

Đặc biệt, không chỉ kiểm tra một trang đầu. Hãy đặt object không được phép ở nhiều vị trí trong tập kết quả để xác minh phân trang được áp dụng sau khi giới hạn quyền. Nếu hệ thống phân trang theo cursor, thử cursor được tạo bởi user khác hoặc tenant khác.

## 10. Kiểm thử object lồng nhau, batch và tác vụ nền

### Object lồng nhau

Với `/api/orders/{orderId}/items/{itemId}`, tạo Order A1 thuộc Alice và Item B1 thuộc Order B1 của Bob. Alice không được truy cập Item B1 chỉ vì biết `itemId`. Cũng cần thử kết hợp `orderId` của Alice với `itemId` của Bob để bảo đảm quan hệ parent-child được kiểm tra.

### Batch và bulk

Gửi một request có ID thuộc Alice và ID thuộc Bob. Nếu contract là all-or-nothing, toàn bộ request phải thất bại và không có object nào bị thay đổi. Nếu contract cho phép partial result, response phải thể hiện rõ kết quả từng phần mà không tiết lộ thông tin nhạy cảm của object bị từ chối. Không được âm thầm xử lý ID trái phép.

### Tác vụ bất đồng bộ

Tạo export job khi Alice có quyền, sau đó thu hồi quyền trước khi worker thực thi. Xác minh chính sách đã định: worker kiểm tra lại quyền tại thời điểm chạy, hoặc job được cấp snapshot quyền có thời hạn và scope được phê duyệt. Không để queue message chứa object ID tùy ý rồi worker truy xuất bằng service account quá rộng.

## 11. Kiểm tra quyền ủy quyền và trạng thái nghiệp vụ

Authorization có thể phụ thuộc grant thay vì chỉ owner. Tạo test cho các trường hợp:

- Support agent có grant `READ` còn hiệu lực được xem object.
- Cùng agent không có grant `UPDATE` nên không sửa được object.
- Grant hết hạn hoặc bị revoke thì request tiếp theo bị từ chối.
- Grant thuộc tenant A không áp dụng cho object tenant B.
- Người cấp quyền mất quyền chia sẻ thì hành vi tiếp theo tuân theo policy đã định.
- Quyền delegated không tự động được chuyển tiếp nếu policy không cho phép.

Ngoài quyền object, kiểm tra business state. Owner vẫn có thể bị từ chối nếu hóa đơn đã khóa, đơn hàng đã giao hoặc yêu cầu hoàn tiền đã xử lý. Một test authorization tốt phải tách được lý do bị từ chối: thiếu quyền chức năng, sai owner/tenant, grant không hợp lệ hay trạng thái nghiệp vụ cấm.

## 12. Chọn status code và kiểm tra rò rỉ thông tin

API có thể dùng `403 Forbidden` để thể hiện caller đã xác thực nhưng không có quyền, hoặc dùng `404 Not Found` cho cả object không tồn tại và object ngoài phạm vi nhằm hạn chế enumeration. Test phải bám theo contract đã chọn.

Ngoài mã trạng thái, so sánh:

- Response body, error code và message.
- Header, redirect và metadata phân trang.
- Sự khác biệt rõ rệt về thời gian xử lý có thể giúp dò object.
- Response có vô tình chứa một phần dữ liệu trước khi trả lỗi hay không.
- Error handler hoặc log có đưa chi tiết nội bộ trở lại client không.

Không yêu cầu thời gian response tuyệt đối giống nhau bằng delay nhân tạo. Tập trung loại bỏ khác biệt không cần thiết và bảo đảm dữ liệu không được truy xuất hoặc trả ra trước khi authorization hoàn tất.

## 13. Kiểm thử cache và các lớp trung gian

Cache có thể làm mất hiệu lực authorization nếu response riêng tư được lưu theo URL chung. Với cùng URL, thực hiện request lần lượt bằng Alice và Bob rồi xác minh Bob không nhận response đã cache của Alice.

Kiểm tra các lớp có thể cache:

- CDN hoặc reverse proxy.
- API gateway.
- Application cache.
- Cache của ORM hoặc query layer.
- Browser cache và service worker.

Với response phụ thuộc principal hoặc tenant, cần policy cache phù hợp như `private` hoặc `no-store`, partition cache theo security context khi thật sự cần cache, và invalidation khi quyền hoặc quan hệ object thay đổi. Không dựa vào cache key khó đoán để bảo vệ dữ liệu.

## 14. Tổ chức bộ test theo endpoint và quyền

Một bảng theo dõi giúp bảo đảm không bỏ sót endpoint:

| Endpoint | Read own | Read other user | Read other tenant | Write other user | No authority | Side effect check |
|---|---:|---:|---:|---:|---:|---:|
| `GET /invoices/{id}` | ✓ | ✓ | ✓ | N/A | ✓ | N/A |
| `PATCH /invoices/{id}` | N/A | N/A | N/A | ✓ | ✓ | ✓ |
| `DELETE /invoices/{id}` | N/A | N/A | N/A | ✓ | ✓ | ✓ |
| `GET /invoices` | ✓ | ✓ | ✓ | N/A | ✓ | N/A |
| `POST /invoices/bulk-export` | ✓ | ✓ | ✓ | N/A | ✓ | ✓ |
| `POST /orders/{id}/cancel` | N/A | N/A | N/A | ✓ | ✓ | ✓ |

Các dấu ✓ biểu thị tình huống cần có test; `N/A` nghĩa là cột không áp dụng trực tiếp. Với mỗi endpoint, bổ sung test cho tenant, delegated grant, trạng thái nghiệp vụ, trường dữ liệu và các đường truy cập phụ phù hợp.

Có thể dùng parameterized test để chạy cùng một policy matrix với nhiều actor/object. Tuy nhiên, đừng chỉ tạo test chung cho helper authorization rồi cho rằng mọi controller đều an toàn. Cần có integration test qua endpoint thật để phát hiện nơi controller, service hoặc repository quên áp dụng policy.

## 15. Tích hợp vào CI và thu thập bằng chứng

Cross-user/cross-tenant tests nên chạy tự động trong pipeline trước khi merge hoặc release. Bộ kiểm tra có thể chia thành:

1. **Unit tests:** kiểm tra policy quyết định đúng với actor, action, object, tenant và grant.
2. **Integration tests:** gọi endpoint qua security filter chain, service và database thật hoặc database test tương đương.
3. **Contract tests:** xác minh status code, schema response, lỗi và hành vi list/bulk theo hợp đồng.
4. **End-to-end tests:** xác minh luồng quan trọng như tải hóa đơn, hủy đơn, hoàn tiền hoặc export.
5. **Security regression tests:** giữ lại test cho các lỗi BOLA/IDOR từng được phát hiện để ngăn tái xuất hiện.

Evidence nên lưu mã test, endpoint/version, principal/tenant fixture, object reference giả lập, kết quả CI và trạng thái dữ liệu sau request. Không đưa token, dữ liệu thật hoặc bí mật vào artifact test. Nếu một test bị bỏ qua, pipeline cần thể hiện rõ lý do và người chấp nhận rủi ro; không tính skipped là passed.

Khi phát hiện lỗi, ghi nhận endpoint, action, loại object, phạm vi user/tenant bị ảnh hưởng, cách tái hiện bằng dữ liệu giả lập và side effect có thể xảy ra. Sau khi sửa, thêm regression test cho cả trường hợp bị từ chối và trường hợp hợp lệ để tránh khóa nhầm người dùng có quyền.

## 16. Checklist cross-user và cross-tenant

- [ ] Có ít nhất hai user trong cùng tenant và hai tenant độc lập.
- [ ] Có fixture cho owner, người không sở hữu, delegated user, service account và anonymous.
- [ ] Ma trận actor/action/object/tenant được xác định trước khi viết test.
- [ ] Test đọc, sửa, xóa, export và thao tác nghiệp vụ trên object của người khác.
- [ ] Test thay ID ở path, query, body, header và object lồng nhau.
- [ ] Test không thể giả mạo `ownerId`, `userId` hoặc `tenantId` bằng dữ liệu client gửi.
- [ ] Test list, search, pagination, aggregate và bulk chỉ trả dữ liệu được phép.
- [ ] Test xác minh database, event, notification, file và downstream không bị thay đổi khi request bị từ chối.
- [ ] Test grant đúng action, grant hết hạn, grant bị revoke và trạng thái nghiệp vụ cấm.
- [ ] Test response, status code, cache và metadata không tiết lộ dữ liệu ngoài policy.
- [ ] Test chạy qua endpoint/security filter chain thực tế và có regression coverage trong CI.
- [ ] Fixture dùng dữ liệu giả lập; artifact không chứa token hoặc dữ liệu production.

## Kết luận

Test truy cập object của user hoặc tenant khác phải chứng minh rằng quyền được thực thi ở mọi đường truy cập và ở cả thời điểm đọc lẫn ghi. Hãy tạo fixture có nhiều owner, tenant và quan hệ ủy quyền; lập ma trận actor/action/object; gọi endpoint thật bằng principal khác nhau; rồi kiểm tra response, database và side effect. Kết hợp unit test policy với integration test, contract test và regression test trong CI giúp phát hiện BOLA, sai phạm tenant isolation và các lỗi phân quyền tái xuất hiện trước khi chúng đến production.
