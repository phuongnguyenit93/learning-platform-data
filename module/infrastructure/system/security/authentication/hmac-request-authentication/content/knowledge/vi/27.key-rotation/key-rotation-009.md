# Rotation khẩn cấp trong HMAC request authentication

## 1. Rotation khẩn cấp là gì và khi nào cần thực hiện?

Trong hệ thống **xác thực HTTP request bằng HMAC với shared secret**, mỗi client dùng một credential gồm định danh khóa (key ID hoặc cặp client ID + key version) và secret để tạo chữ ký của **canonical request**. Server tra cứu đúng secret, tái tạo canonical request theo hợp đồng ký rồi xác minh HMAC. Khi secret có nguy cơ bị lộ, kẻ tấn công sở hữu nó có thể tạo **chữ ký HMAC hợp lệ cho các request giả mạo**. Timestamp và nonce giúp chống phát lại request cũ, nhưng **không ngăn người đã có secret tạo request mới với timestamp và nonce mới**.

**Rotation khẩn cấp (emergency key rotation)** là quy trình thay thế và vô hiệu hóa một hoặc nhiều thế hệ secret trong thời gian ứng phó sự cố, với mục tiêu thu hẹp nhanh nhất khoảng thời gian secret không còn đáng tin cậy vẫn có thể được dùng để xác thực. Nó khác với rotation theo lịch ở chỗ ưu tiên **chặn credential nguy hiểm**, dù các client đang dùng credential đó có thể bị gián đoạn.

Các tín hiệu kích hoạt thường gặp:

- Secret xuất hiện trong log, ticket, email, file cấu hình, kho mã nguồn hoặc artifact công khai/ngoài phạm vi kiểm soát.
- Thiết bị, CI runner, máy chủ, kho cấu hình hoặc secret manager có quyền đọc shared secret bị xâm nhập hoặc nghi xâm nhập.
- Phát hiện request được ký bằng credential hợp lệ nhưng không khớp với hoạt động đã biết của client; nghi có người khác sở hữu secret.
- Nhân sự/tích hợp mất quyền tin cậy nhưng vẫn nắm secret đã cấp; đối tác báo thất lạc credential.
- Chính sách vận hành yêu cầu thay khóa ngay sau sự cố hoặc sai sót cấp phát có tác động lớn.

**Phân biệt sự kiện và kết luận:** một lượng lớn lỗi HMAC có thể do canonicalization qua proxy/gateway, cấu hình version hoặc clock skew; chưa đủ chứng minh secret đã bị lộ. Tuy nhiên, nếu rủi ro sử dụng trái phép đủ cao, vẫn có thể **tạm khóa trước để điều tra**. Quyết định cần được ghi nhận cùng lý do và người phê duyệt theo quy trình ứng phó sự cố.

### So sánh rotation thông thường và rotation khẩn cấp

| Tiêu chí | Rotation theo lịch | Rotation khẩn cấp khi nghi lộ |
| --- | --- | --- |
| Mục tiêu ưu tiên | Thay khóa có kế hoạch, giữ tương thích | Chặn khả năng dùng secret không còn tin cậy |
| Hai khóa cùng ACTIVE | Có thể chấp nhận trong cửa sổ chuyển tiếp | Không duy trì khóa nghi lộ để phục vụ chuyển tiếp |
| Thời điểm kết thúc khóa cũ | Theo lịch rollout và điều kiện hoàn tất | Càng sớm càng tốt sau quyết định thu hồi, có cơ chế cưỡng chế |
| Cấp khóa mới | Có thể chuẩn bị và thử nghiệm trước | Tạo/cấp phát qua kênh tin cậy trong điều kiện sự cố |
| Tác động đến client | Cố gắng tránh gián đoạn | Gián đoạn có thể cần thiết để bảo vệ hệ thống |
| Theo dõi | Tiến độ chuyển đổi, tỷ lệ lỗi | Tốc độ thu hồi thực tế, lạm dụng, phục hồi, phạm vi ảnh hưởng |
| Hoàn tác | Có thể quay về khóa cũ khi còn đáng tin cậy | Không tái kích hoạt secret đã xác định là bị lộ |

Đặc biệt, **phát hành secret mới chưa đồng nghĩa hoàn tất rotation**. Nếu secret cũ vẫn ACTIVE hoặc một gateway vẫn chấp nhận nó từ cache, khả năng giả mạo vẫn tồn tại.

## 2. Phạm vi ảnh hưởng và quyết định khẩn cấp

Trước khi sửa trạng thái, cần định danh chính xác *đối tượng mất tin cậy*:

| Trường hợp | Phạm vi xử lý tối thiểu |
| --- | --- |
| Chỉ secret của client A, key version K7 bị lộ | Thu hồi K7 của A; đánh giá các version khác có thể đã bị truy cập |
| File chứa nhiều secret client bị lộ | Thu hồi toàn bộ credential nằm trong file hoặc có khả năng lộ |
| Một principal có nhiều key và mọi key có thể đã bị đọc | Vô hiệu hóa các credential liên quan của principal trước khi cấp mới |
| Secret manager hoặc pipeline cấp phát bị xâm nhập | Điều tra phạm vi quyền truy cập; có thể cần thu hồi theo nhóm, cô lập nguồn cấp phát |
| Không chắc secret nào đã lộ, nhưng có bằng chứng về truy cập trái phép | Áp dụng biện pháp ngăn chặn theo phạm vi xấu nhất có cơ sở; thu hẹp sau điều tra |

Key ID là định danh **tra cứu**, không phải ranh giới tin cậy độc lập. Một secret có thể được dùng ở nhiều service do thiết kế cũ, vì vậy cần xác định các verifier, gateway, region và môi trường (production, staging) cùng tin vào nó. Nếu cùng secret đã được dùng ở nhiều môi trường, tất cả nơi sử dụng cần được xử lý theo phạm vi ảnh hưởng đã xác minh.

Một quyết định khẩn cấp cần trả lời bốn câu hỏi:

1. **Khóa nào cần dừng ngay?** Xác định client/principal, key ID, key version, trạng thái hiện tại, môi trường và thời gian phát hiện.
2. **Có cần chặn cả client trước khi phát khóa mới?** Khi không thể xác định version bị lộ hoặc quyền tin cậy của client cũng bị xâm phạm, có thể tạm khóa toàn bộ credential của principal.
3. **Cách nào bảo đảm mọi verifier đều chặn?** Xác định nguồn trạng thái có thẩm quyền và cơ chế cache/invalidation; nếu không chứng minh được độ mới, áp dụng fail closed cho phạm vi bị ảnh hưởng.
4. **Đường cấp khóa mới có còn đáng tin không?** Không gửi secret mới qua kênh vừa bị xâm phạm hoặc chỉ dựa vào credential bị lộ để xác nhận người nhận.

Trong trường hợp phải lựa chọn giữa gián đoạn dịch vụ và tiếp tục chấp nhận secret đã biết bị lộ, không nên âm thầm kéo dài cửa sổ chấp nhận. Mọi quyết định ngoại lệ phải được người có thẩm quyền đánh giá, ghi nhận và giới hạn phạm vi; chính sách an toàn của hệ thống nên mặc định **không dùng lại khóa bị thu hồi**.

## 3. Mô hình credential và trạng thái khi thu hồi

Ví dụ một hệ thống dùng cặp (client_id, key_version) để chọn đúng secret:

| client_id | key_version | state | valid_from | expires_at | secret_ref |
| --- | --- | --- | --- | --- | --- |
| partner-a | 7 | REVOKED | 2026-10-01 | 2027-01-01 | vault/partner-a/k7 |
| partner-a | 8 | ACTIVE | 2026-11-28 | 2027-02-01 | vault/partner-a/k8 |

Ở thời điểm sau sự cố, mọi request khai version 7 phải bị từ chối **dù chữ ký K7 vẫn chính xác và expires_at chưa đến**. Request version 8 chỉ được xét tiếp nếu K8 thực sự đã được cấp cho client tin cậy, còn hiệu lực, có chữ ký đúng, timestamp/nonce hợp lệ và được phân quyền.

Một mô hình vòng đời minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Phát hành phiên bản mới
    PENDING --> ACTIVE: Kích hoạt sau kiểm tra
    ACTIVE --> SUSPENDED: Cô lập tạm thời
    SUSPENDED --> ACTIVE: Gỡ tạm khóa sau điều tra
    ACTIVE --> REVOKED: Thu hồi khẩn cấp
    SUSPENDED --> REVOKED: Xác nhận lộ khóa
    ACTIVE --> RETIRED: Ngừng theo kế hoạch
    REVOKED --> [*]
    RETIRED --> [*]
~~~

Các bất biến bảo mật quan trọng:

- **REVOKED** là trạng thái kết thúc đối với version đã bị coi là mất tin cậy; không chuyển lại thành ACTIVE. Nếu cần khôi phục dịch vụ, tạo một version mới với secret mới.
- Trạng thái ACTIVE không đủ để được chấp nhận: server còn phải kiểm tra valid_from ≤ **thời gian server** < expires_at và cờ thu hồi nếu có.
- Không thay secret bên dưới cùng key ID/version. Mỗi phiên bản định danh một secret bất biến; tránh cache và audit bị lẫn thế hệ khóa.
- Một key version mới phải trỏ tới secret được tạo độc lập bằng nguồn ngẫu nhiên mật mã (CSPRNG); không dùng bản sao, không ghép thêm hậu tố để suy ra secret mới từ secret cũ.
- Không tin header “latest” hoặc tự động thử các khóa cũ khi chữ ký với khóa khai báo thất bại.
- Thu hồi credential phục vụ **xác thực**. Quyền được gọi API vẫn do chính sách **phân quyền** quyết định sau xác thực.

Việc chỉ sửa một trường `is_current` hoặc đặt K8 thành “default” sẽ không bảo vệ được hệ thống nếu K7 vẫn được chấp nhận trong phần xác minh HMAC.

## 4. Runbook ứng phó: từ phát hiện đến phục hồi

Quy trình sau giả định có registry trạng thái credential tập trung hoặc có nguồn dữ liệu chuẩn, hệ thống quản lý secret, đội vận hành gateway và người phụ trách client. Tên vai trò có thể điều chỉnh cho tổ chức, nhưng trách nhiệm quyết định và kiểm chứng phải rõ.

### Bước 1 — Tiếp nhận cảnh báo và lưu bằng chứng

Ghi lại thời điểm phát hiện (UTC), người báo, môi trường, client/principal, key ID hoặc version, vị trí nghi lộ và các request đáng ngờ có correlation ID. Nếu nguồn lộ là log hoặc repository, hạn chế truy cập ngay và lưu bằng chứng theo quy trình sự cố. **Không sao chép giá trị secret vào ticket, báo cáo, chat, log thử nghiệm hoặc lệnh shell**.

Tách ba mốc: thời điểm *có thể đã lộ*, thời điểm *phát hiện*, và thời điểm *thực tế không còn được verifier chấp nhận*. Khoảng giữa các mốc quan trọng để điều tra các request đã được chấp nhận trong thời gian ảnh hưởng.

### Bước 2 — Chặn sử dụng credential cũ

Ghi trạng thái K7 thành SUSPENDED nếu phải cô lập ngay khi điều tra, hoặc REVOKED khi đã xác định phải thay thế. Quyết định phải đi qua kênh quản trị có xác thực và phân quyền riêng, với thay đổi được kiểm toán.

Nếu không thể tra cứu/thu hồi đúng version do hệ thống quản trị gặp sự cố, dùng cơ chế **khóa khẩn cấp ở lớp verifier hoặc gateway** theo principal/key ID để chặn tại điểm xác thực, kèm quy trình đồng bộ trạng thái nguồn sau đó. Cơ chế này phải có quyền truy cập hạn chế và fail closed khi không thể chứng minh bản khóa đang an toàn.

**Không chờ phát hành K8 thành công mới bắt đầu chặn K7 bị lộ.** Việc chậm thu hồi để tránh downtime kéo dài cửa sổ giả mạo.

### Bước 3 — Phát hành version và secret mới

Tạo K8 mới với key ID/version **chưa từng dùng**, secret ngẫu nhiên độc lập, ref tới nơi lưu secret bảo vệ bởi vault/KMS hoặc dịch vụ quản lý bí mật phù hợp. Cấp phát theo giao dịch để tránh hai tác vụ đồng thời chọn trùng version. Đặt trạng thái K8 là PENDING khi còn kiểm tra dữ liệu và kênh cấp phát.

Không tái sử dụng secret cũ, không lưu secret rõ trong registry, không đưa vào logs/metrics, không copy sang công cụ hỗ trợ không có kiểm soát. Nếu nguồn cấp phát cũ bị xâm nhập, cần dựng đường cấp phát tin cậy trước khi tạo khóa mới; nếu không, K8 có thể bị lộ ngay sau khi phát hành.

### Bước 4 — Chuyển giao qua kênh an toàn và kích hoạt

Xác minh người/ứng dụng nhận secret mới bằng một phương thức tin cậy **độc lập với credential bị nghi lộ**; ví dụ qua kênh quản trị có MFA và phân quyền phù hợp, workload identity hoặc một quy trình cấp phát đã được bảo vệ. Không đặt secret mới trong email/ticket dưới dạng rõ.

Kiểm thử client tạo chữ ký bằng K8 với hợp đồng canonical request đang được hỗ trợ; chỉ sau khi verifier sẵn sàng tra cứu K8 và dữ liệu đã đồng bộ, chuyển K8 sang ACTIVE. Client cập nhật cả **secret và key ID/version**, tránh cấu hình version 8 nhưng vẫn ký bằng K7.

### Bước 5 — Xác nhận mọi điểm xác thực đã chặn K7

Đọc trạng thái nguồn REVOKED mới là một phần công việc. Phải kiểm tra K7 trên từng nhóm instance, gateway, region và lớp cache có liên quan. Gửi các request thử nghiệm phù hợp với môi trường, gồm request HMAC hợp lệ **được tạo bằng khóa thử đã kiểm soát** trong quy trình kiểm thử, để đo xem node nào còn chấp nhận key bị thu hồi.

Không phơi bày secret thực đang nghi lộ trong công cụ đo hoặc log. Khi không thể chạy kiểm thử chủ động bằng một key production đã bị lộ, dựa vào phép đo độ mới/ack của các điểm xác thực và bài test tương đương trên môi trường kiểm soát, đồng thời áp dụng chính sách chặn tại verifier.

### Bước 6 — Giám sát phục hồi và điều tra sau thu hồi

Quan sát request dùng version cũ sau thời điểm thu hồi, tăng đột biến các lỗi HMAC, lỗi do key ID không tồn tại, thất bại replay và phần trăm client đã chuyển sang K8. Các request bằng K7 còn xuất hiện có thể là client chưa cập nhật, tác vụ nền cũ, hoặc người tấn công tiếp tục thử.

Sau khi dịch vụ phục hồi, đánh giá request đã được chấp nhận trong cửa sổ nghi lộ, điều tra tác động nghiệp vụ và triển khai các biện pháp khắc phục nguồn lộ. Nếu có khả năng kẻ tấn công còn truy cập môi trường client hoặc kênh cấp phát, chỉ thay secret chưa đủ; phải khắc phục điểm xâm nhập trước khi coi sự cố đã kết thúc.

### Luồng tổng quát

~~~mermaid
flowchart TD
    A["Phát hiện nghi lộ shared secret"] --> B["Xác định client, version, phạm vi và nguồn lộ"]
    B --> C["Khóa/REVOKE credential bị ảnh hưởng"]
    C --> D["Đồng bộ chặn đến gateway, verifier và cache"]
    C --> E["Tạo K mới qua hệ thống cấp phát tin cậy"]
    E --> F["Xác minh người nhận, phân phối và kiểm thử ký"]
    F --> G["Kích hoạt K mới và chuyển client"]
    D --> H["Đo xác nhận K cũ bị từ chối trên các node"]
    G --> I["Giám sát client và khả năng phục hồi"]
    H --> J["Điều tra tác động và đóng sự cố"]
    I --> J
~~~

Hai nhánh “chặn khóa cũ” và “cấp khóa mới” có thể diễn ra song song dưới sự phối hợp của người xử lý sự cố, nhưng **độ an toàn không được phụ thuộc vào việc client đã chuyển xong**.

## 5. Đảm bảo thu hồi có hiệu lực trong hệ thống nhiều instance

Một lỗi nguy hiểm trong emergency rotation là database đã ghi REVOKED nhưng server xác thực vẫn dùng cache chứa ACTIVE.

Giả sử:

- 10:00:00: Gateway B cache K7=ACTIVE với TTL 60 giây.
- 10:00:10: Hệ thống quản trị commit K7=REVOKED trong registry.
- 10:00:20: Request ký bằng K7 đi qua B.

Nếu B chỉ đọc cache đến 10:01:00, nó **có thể vẫn chấp nhận** request tại 10:00:20. Vì vậy không thể khẳng định “thu hồi tức thì” chỉ nhờ update database hoặc phát thông báo bất đồng bộ.

Các cách giảm độ trễ và tăng độ chắc chắn:

| Cơ chế | Lợi ích | Giới hạn cần hiểu |
| --- | --- | --- |
| Cache TTL ngắn | Giới hạn tuổi dữ liệu trong trường hợp bình thường | Vẫn có cửa sổ stale; TTL không đảm bảo tức thì |
| Push invalidation tới mọi gateway | Giảm độ trễ khi các node nhận thông báo | Node mất mạng hoặc restart có thể bỏ lỡ |
| Outbox + event có revision | Giúp event phát lại, không áp dụng trạng thái cũ lên mới | Vẫn cần theo dõi lag và xác nhận phía consumer |
| Kiểm tra denylist thu hồi cập nhật thường xuyên | Chặn nhanh một key ID/version cụ thể | Denylist cũng có freshness và tính sẵn sàng cần quản lý |
| Đọc trạng thái có thẩm quyền trước khi chấp nhận | Tăng độ chắc chắn tại điểm quyết định | Phụ thuộc latency, availability và nhất quán của nguồn đọc |
| Emergency block ở gateway/verifier | Cô lập nhanh theo principal hoặc key | Phải đồng bộ đủ mọi điểm vào và không được bỏ sót đường đi thay thế |

**Điểm quyết định an toàn:** nếu yêu cầu của hệ thống là *mọi request bắt đầu sau khi commit thu hồi đều không được chấp nhận*, thì mỗi verifier phải có cơ chế chứng minh trạng thái nó đang dùng **không cũ hơn commit đó**, hoặc phải từ chối khi không thể chứng minh. Chỉ đẩy event bất đồng bộ và đặt TTL sẽ không đáp ứng một cam kết mạnh như vậy. Yêu cầu này còn cần định nghĩa thời điểm “bắt đầu”, trường hợp request đã vượt qua kiểm tra trước commit và các đường tiếp nhận request không qua gateway thông thường.

Có thể dùng **epoch/revision theo credential hoặc principal** để ngăn nhận lại trạng thái cũ: cache chỉ cập nhật nếu revision mới lớn hơn revision đã có. Một sự kiện đến muộn với revision thấp hơn phải bị bỏ qua. Tuy nhiên, việc chống rollback revision **không tự chứng minh cache đang mới nhất** nếu node không nhận được sự kiện mới.

Khi registry, vault hoặc kho trạng thái thu hồi không khả dụng, không được coi việc không đọc được trạng thái là ACTIVE. Xác thực nên **fail closed** theo phạm vi cần bảo vệ, ghi metric/alert và đưa incident vào kênh xử lý sự cố.

## 6. Mẫu cập nhật trạng thái nguyên tử, có kiểm toán

Ví dụ PostgreSQL dưới đây minh họa cách thu hồi một key version đang ACTIVE hoặc SUSPENDED bằng điều kiện revision để tránh thao tác song song ghi đè. Giả sử các bảng hmac_credentials và security_outbox đã tồn tại theo thiết kế dự án.

~~~sql
BEGIN;

UPDATE hmac_credentials
SET lifecycle_state = 'REVOKED',
    revoked_at = CURRENT_TIMESTAMP,
    state_changed_at = CURRENT_TIMESTAMP,
    row_version = row_version + 1
WHERE client_id = :client_id
  AND key_version = :compromised_version
  AND lifecycle_state IN ('ACTIVE', 'SUSPENDED')
  AND row_version = :expected_row_version
RETURNING client_id, key_version, lifecycle_state, row_version;

-- Ứng dụng phải xác minh UPDATE trả đúng 1 hàng.
-- Nếu trả 0 hàng: ROLLBACK, đọc lại trạng thái và xử lý xung đột/idempotency.
-- Chỉ khi UPDATE thành công: ghi outbox trong CÙNG transaction.
INSERT INTO security_outbox (
    event_id,
    event_type,
    aggregate_key,
    event_payload,
    created_at
) VALUES (
    :event_id,
    'HMAC_KEY_REVOKED',
    :aggregate_key,
    :event_payload,
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Đây là **mẫu ý tưởng**, không phải script có thể chạy độc lập: các named parameter, bảng outbox và điều kiện kiểm tra số hàng cập nhật cần do tầng ứng dụng triển khai. event_payload nên chỉ chứa client/key version, trạng thái mới, revision, timestamp, correlation ID và lý do; **không chứa secret hoặc chữ ký HMAC**. Nếu UPDATE không cập nhật bản ghi vì khóa đã REVOKED, kiểm tra trạng thái hiện hành và ghi nhận thao tác idempotent phù hợp, không chuyển key về ACTIVE.

Nếu cần thu hồi hàng loạt nhiều phiên bản của cùng principal, hãy xác định tập mục tiêu rồi cập nhật bằng transaction có cơ chế kiểm soát cạnh tranh. Trường hợp phải vô hiệu hóa toàn principal ngay có thể dùng cờ khóa ở cấp principal và buộc tất cả verifier kiểm tra cờ này tại điểm xác thực. Phát hành K8 là một quy trình riêng, không được âm thầm xóa trạng thái REVOKED của K7.

**Audit tối thiểu:** người/tiến trình yêu cầu, lý do và mã sự cố, môi trường, key ID/version, trạng thái trước/sau, revision, thời điểm commit, thời điểm event tới verifier, cùng người xác minh kết quả chặn. Quyền đọc và lưu trữ audit cần được kiểm soát, tránh vô tình ghi dữ liệu nhạy cảm.

## 7. Kiểm tra request sau emergency rotation

Ví dụ client partner-a có K7 bị thu hồi và K8 mới ACTIVE. Server nhận:

~~~http
POST /v1/payments?mode=instant HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Version: 7
X-Timestamp: 2026-11-28T03:10:00Z
X-Nonce: bcf0e0b7-4b4e-49a5-9ed9-aa75a4667e90
X-Signature: <chu-ky-minh-hoa>

{"amount":100000}
~~~

Dù đây là chữ ký hợp lệ bằng secret K7, server vẫn phải từ chối do K7=REVOKED. HMAC không bao hàm quyền sử dụng vô hạn; trạng thái credential được kiểm tra độc lập với phép tính chữ ký.

Một luồng quyết định minh họa:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway / Verifier
    participant R as Credential registry
    participant N as Nonce store
    C->>G: Request + clientId + keyVersion + signature
    G->>R: Tra đúng keyId/version và trạng thái hiện hành
    R-->>G: K7=REVOKED hoặc K8=ACTIVE
    alt Key đã REVOKED hoặc trạng thái không chứng minh được
        G-->>C: Authentication failed
    else Key ACTIVE và còn hiệu lực
        G->>G: Dựng canonical request, kiểm tra HMAC bằng đúng key
        G->>G: Kiểm tra timestamp
        G->>N: Đăng ký nonce atomically nếu chưa dùng
        N-->>G: Mới hoặc trùng
        G->>G: Xác định principal và kiểm tra authorization
        G-->>C: Kết quả yêu cầu
    end
~~~

Các điểm quan trọng:

- **Không fallback:** request khai K7 không được xác minh tiếp bằng K8 nếu thất bại; request khai K8 không được thử secret K7.
- **Ràng buộc định danh khóa vào hợp đồng ký:** key ID/version, client ID, timestamp, nonce và các thành phần canonical request cần được xác định chính xác, ký theo cùng quy tắc ở hai phía. Không chấp nhận nhiều giá trị header mơ hồ.
- **Timestamp/nonce không thay thế rotation:** kẻ đã có K7 có thể tạo chữ ký và nonce mới, nên chỉ thu hồi thực tế mới chặn được. Nonce vẫn phải được ghi atomically trên kho dùng chung giữa các instance sau khi xác minh chữ ký; TTL phải bao phủ cửa sổ chấp nhận timestamp.
- **Không lấy timestamp client để quyết định expires_at:** dùng thời gian server cho hiệu lực credential, dùng timestamp của request để đánh giá replay.
- **Phân biệt 401/403:** thất bại xác thực vì key bị thu hồi thường dùng phản hồi 401 theo hợp đồng API; 403 là trường hợp principal đã được xác thực nhưng bị từ chối phân quyền. Không tiết lộ “key tồn tại nhưng bị thu hồi” cho đối tượng không đáng tin cậy.
- **Gateway/proxy:** đảm bảo ký và xác minh cùng method, URI, query, header và body/digest theo hợp đồng; rewrite ở proxy gây SIGNATURE_MISMATCH nhưng không phải bằng chứng trực tiếp của secret bị lộ.

### Ví dụ Java: quyết định khả dụng của một key version

Đoạn Java 17 này **chỉ** đánh giá trạng thái và thời hạn, không tính chữ ký. Nó cho thấy lý do phải tách “phiên bản đúng” khỏi “phiên bản được phép dùng”.

~~~java
import java.time.Instant;

public final class EmergencyCredentialPolicy {
    enum State { PENDING, ACTIVE, SUSPENDED, REVOKED, RETIRED }
    enum Decision {
        ACCEPT_FOR_HMAC_CHECK,
        UNKNOWN_KEY,
        NOT_ACTIVE,
        REVOKED,
        NOT_YET_VALID,
        EXPIRED
    }

    record Credential(
        String clientId,
        int keyVersion,
        State state,
        Instant validFrom,
        Instant expiresAt,
        Instant revokedAt,
        long rowVersion
    ) {}

    static Decision evaluate(
        Credential credential,
        String requestedClient,
        int requestedVersion,
        Instant serverNow
    ) {
        if (credential == null
                || !credential.clientId().equals(requestedClient)
                || credential.keyVersion() != requestedVersion) {
            return Decision.UNKNOWN_KEY;
        }
        if (credential.state() == State.REVOKED
                || credential.revokedAt() != null) {
            return Decision.REVOKED;
        }
        if (credential.state() != State.ACTIVE) {
            return Decision.NOT_ACTIVE;
        }
        if (serverNow.isBefore(credential.validFrom())) {
            return Decision.NOT_YET_VALID;
        }
        if (!serverNow.isBefore(credential.expiresAt())) {
            return Decision.EXPIRED;
        }
        return Decision.ACCEPT_FOR_HMAC_CHECK;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-28T03:12:00Z");
        Credential oldKey = new Credential(
            "partner-a", 7, State.REVOKED,
            Instant.parse("2026-10-01T00:00:00Z"),
            Instant.parse("2027-01-01T00:00:00Z"),
            Instant.parse("2026-11-28T03:11:00Z"),
            5
        );

        System.out.println(evaluate(oldKey, "partner-a", 7, now));
        // REVOKED, dù chưa hết hạn và secret có thể tính HMAC đúng.
    }
}
~~~

Ứng dụng thực tế phải tra cứu credential theo đúng định danh, kiểm tra freshness/cache, lấy secret qua kho được bảo vệ, tính và so sánh HMAC an toàn về timing, kiểm tra timestamp/nonce rồi phân quyền. Hàm `evaluate` không chứng minh request an toàn nếu snapshot credential bị cũ hoặc các bước xác minh còn thiếu. Nên sử dụng `Clock` được tiêm để kiểm thử chính xác các mốc thời gian.

## 8. Phân phối khóa mới và phục hồi client khi đang có sự cố

Trong tình huống bình thường, đội client có thể triển khai K8 theo kế hoạch. Trong tình huống khẩn cấp, phải xử lý thêm nguy cơ hệ thống phân phối secret hoặc môi trường client đã bị truy cập trái phép.

**Cấp phát K8 an toàn:**

1. Xác định nơi tạo secret và tài khoản có quyền đọc; kiểm tra nguồn đó không thuộc phạm vi nghi bị xâm phạm. Nếu có, cô lập và thay cơ chế cấp phát trước.
2. Sinh secret bằng CSPRNG với độ dài/entropy đáp ứng chính sách mật mã; lưu bằng hệ thống secret manager, hạn chế quyền đọc theo workload và môi trường.
3. Gắn K8 với version/key ID mới, principal đúng và hợp đồng canonical request/thuật toán đã được duyệt. Không cho client tùy ý chỉ định thuật toán yếu hơn.
4. Xác thực đối tác nhận secret qua kênh được bảo vệ và quy trình xác minh độc lập; không dùng credential K7 bị lộ làm chứng cứ duy nhất để nhận K8.
5. Kiểm tra ký request thử với K8 và đúng canonical request qua proxy/gateway thực tế. Chỉ kích hoạt lưu lượng production khi verifier đã tra được K8.
6. Xác nhận sau chuyển đổi: K8 được dùng thành công, K7 tiếp tục bị từ chối, và không có phiên bản bị lộ nào còn tồn tại trong cấu hình runtime.

**Client chưa chuyển kịp:** nên trả lỗi xác thực nhất quán, hỗ trợ kênh khôi phục riêng và ghi nhận thời điểm dự kiến hoàn tất. Không bật lại K7 để “cho client chạy tạm”. Nếu nghiệp vụ cần duy trì dịch vụ quan trọng, cần cân nhắc phương án dự phòng được thiết kế sẵn (ví dụ credential độc lập chưa bị ảnh hưởng hoặc kênh xác thực thay thế được phê duyệt), tránh sử dụng secret đã mất tin cậy.

**Client offline hoặc batch hiếm chạy:** không suy luận “mọi client đã phục hồi” chỉ từ việc không thấy request K7. Cần đối chiếu lịch trình chạy của các client hoặc một danh sách xác nhận của chủ sở hữu; key cũ vẫn phải bị chặn bất kể client đã được cập nhật hay chưa.

## 9. Kiểm tra riêng các tình huống khó

### 9.1. Request đang xử lý lúc thu hồi

Giả sử request dùng K7 đã qua bước HMAC/nonce lúc 10:00:09; K7 bị REVOKED tại 10:00:10; nghiệp vụ ghi dữ liệu lúc 10:00:11. Nếu chính sách chỉ kiểm tra tại điểm xác thực, request đã qua kiểm tra trước commit có thể hoàn thành. Nếu yêu cầu thu hồi cũng hủy thao tác đang chạy, cần một **điểm kiểm tra lại trạng thái trước hành động nhạy cảm** hoặc cơ chế hủy công việc phù hợp. Tài liệu vận hành phải định nghĩa thời điểm cam kết thu hồi có hiệu lực, thay vì mặc nhiên cho rằng tất cả request đang chạy đều bị dừng.

### 9.2. Hệ thống registry/vault mất kết nối

Nếu một region không truy cập nguồn trạng thái, nó có thể đang giữ K7=ACTIVE trong cache. Không chấp nhận tiếp vô hạn bằng cache cũ. Thiết kế phải có TTL/freshness policy hoặc điểm xác nhận online cho trạng thái nhạy cảm; khi không chứng minh trạng thái hiện tại, từ chối và phát cảnh báo. Thời gian khôi phục hệ thống phụ trợ và chính sách giảm lưu lượng cần có sẵn trong runbook.

### 9.3. Sự kiện thu hồi đến sai thứ tự

Key registry phát event revision 6 (REVOKED) rồi consumer nhận muộn event revision 5 (ACTIVE). Consumer không được áp dụng revision 5 đè revision 6. Tuy nhiên, revision monotonic giải quyết chuyện **đảo ngược trạng thái**; vẫn cần phát hiện node hoàn toàn không nhận được revision 6.

### 9.4. Nhiều client hoặc môi trường dùng chung secret

Nếu do sai thiết kế mà cùng secret được dùng bởi A và B, thu hồi chỉ K7 của A chưa đủ: B còn ACTIVE vẫn có thể chấp nhận secret đó. Ưu tiên rà soát bản đồ secret_ref và quyền truy cập để xử lý toàn bộ nơi sử dụng, sau đó tách secret cho từng principal/môi trường. Không để một key ID của client A được tra cứu nhầm vào principal B.

### 9.5. Replay store bị lỗi khi đang rotation

Sau khi K8 ACTIVE, kẻ tấn công vẫn có thể thử phát lại các request hợp lệ đã thu thập nếu hệ thống không kiểm tra nonce/timestamp. Kho replay cần thao tác nguyên tử và phạm vi định danh phù hợp (ví dụ client ID + key version + nonce), dùng chung giữa các verifier. Nếu replay store không khả dụng, không bỏ qua kiểm tra chỉ để “giữ dịch vụ” trừ khi có thiết kế thay thế được đánh giá và phê duyệt trước.

### 9.6. Sai lệch canonical request qua proxy

K8 được cấp đúng nhưng client ký URI trước rewrite, trong khi verifier lấy URI sau rewrite; chữ ký không khớp. Điều tra bằng các trường không nhạy cảm như version hợp đồng ký, mã route, độ dài payload, digest kiểm thử trong môi trường kiểm soát và correlation ID. Không in secret, canonical request chứa dữ liệu nhạy cảm, full body hay header chữ ký ra log để debug. Một sự cố canonicalization không phải lý do mở lại K7 đã REVOKED.

## 10. Giám sát và tiêu chí đóng sự cố

Vì rotation khẩn cấp đòi hỏi tốc độ và khả năng xác minh, dashboard nên phân biệt trạng thái registry, trạng thái thực thi ở các verifier và tiến độ client.

| Tín hiệu | Ý nghĩa | Hành động khi bất thường |
| --- | --- | --- |
| Thời gian từ phát hiện đến commit REVOKED | Độ nhanh của phản ứng ban đầu | Xem lại quy trình quyền hạn và thao tác quản trị |
| Thời gian từ commit đến mỗi verifier chặn K7 | Hiệu quả lan truyền thu hồi thực tế | Điều tra node/region còn stale, cô lập hoặc fail closed |
| Request bằng key bị REVOKED sau commit | Client cũ hoặc hoạt động đáng ngờ | Phân nhóm theo nguồn, điều tra và hỗ trợ chuyển đổi |
| Request ký đúng bằng K8 | Tiến độ phục hồi trên từng client | Kiểm tra client lâu không tạo request |
| Tỷ lệ lỗi SIGNATURE_MISMATCH theo phiên bản | Sai cấu hình key/version hoặc canonical request | Kiểm tra hợp đồng ký và proxy rewrite |
| Lỗi registry/secret manager/replay store | Nguy cơ không thể xác minh an toàn | Kích hoạt cảnh báo, fail closed, khôi phục phụ trợ |
| Số event invalidation chưa ack / consumer lag | Nguy cơ stale cache | Chặn đường vào không đủ freshness nếu cần |

Metric tổng hợp nên dùng nhãn có số lượng giá trị hữu hạn: môi trường, region, service, mã lý do. Client ID/key version có thể có cardinality lớn và nhạy cảm: dùng log bảo mật được kiểm soát quyền truy cập để điều tra chi tiết. Ghi audit sự kiện REVOKED, K8 ACTIVE, event đã xử lý, kết quả kiểm tra node và mã sự cố; **không ghi secret, chữ ký hoặc body nhạy cảm**.

Không nên chỉ đánh dấu sự cố “đóng” khi K8 ACTIVE. Một bộ tiêu chí kết thúc phù hợp:

- Credential bị ảnh hưởng đã REVOKED hoặc bị chặn có hiệu lực ở **mọi đường xác thực liên quan**, có bằng chứng về độ mới dữ liệu.
- Không còn đường fallback âm thầm chấp nhận secret cũ; trạng thái cache/registry nhất quán theo cam kết của hệ thống.
- Client hợp lệ đã được cấp lại thông tin an toàn và có kế hoạch rõ cho client offline/batch; khôi phục được xác minh bằng request ký K8.
- Phạm vi sử dụng trái phép trong cửa sổ ảnh hưởng đã được điều tra, xử lý tác động nghiệp vụ và lưu audit.
- Nguyên nhân làm lộ secret hoặc kênh cấp phát yếu đã được khắc phục để secret mới không lặp lại rủi ro cũ.

## 11. Bảng kiểm thử cho rotation khẩn cấp

| Tình huống | Kết quả bắt buộc |
| --- | --- |
| K7 vừa REVOKED, request có HMAC K7 đúng | Từ chối xác thực ngay tại verifier đã nhận trạng thái mới |
| K7 chưa hết expires_at nhưng đã REVOKED | Từ chối vì trạng thái, không vì hết hạn |
| K8 đang PENDING, client ký đúng bằng K8 | Từ chối đến khi được kích hoạt |
| K8 ACTIVE, đúng key ID/version, HMAC đúng, timestamp/nonce mới | Đi qua xác thực; còn phải kiểm tra authorization |
| Client khai K8 nhưng ký bằng K7 | Từ chối; không thử các version khác |
| Client khai K7 nhưng ký bằng K8 | Từ chối; không tự chuyển sang K8 |
| K8 HMAC đúng nhưng nonce đã dùng | Từ chối replay trên mọi gateway |
| Header key version trùng hoặc mơ hồ | Từ chối, không tự đoán phiên bản |
| Proxy sửa URI/header/body so với hợp đồng ký | Phát hiện HMAC mismatch, không chấp nhận silent canonicalization |
| Hai thao tác thu hồi song song | Chỉ một cập nhật theo revision; thao tác còn lại xử lý xung đột/idempotency |
| Event ACTIVE revision thấp đến sau REVOKED | Không cho cache phục hồi K7 |
| Một region bỏ lỡ event thu hồi | Region không được tiếp tục chấp nhận K7 khi không chứng minh freshness |
| Registry hoặc vault mất kết nối | Fail closed theo chính sách bảo mật và cảnh báo |
| Người nhận K8 chỉ xác minh bằng credential K7 bị lộ | Không đủ cơ sở cấp secret; dùng kênh tin cậy độc lập |
| Một request đã xác thực trước commit thu hồi | Kết quả phụ thuộc chính sách in-flight được định nghĩa; kiểm tra lại trước hành động nhạy cảm nếu cần |
| K7 đã REVOKED nhưng operator yêu cầu rollback | Không tái kích hoạt K7; phát hành K9 nếu K8 có lỗi và không có key tin cậy khác |

### Kịch bản kiểm thử liên vùng

Hệ thống có ba gateway A, B, C tại ba vùng và cache trạng thái key trong 60 giây. Lúc 10:05:00, phát hiện K7 có khả năng bị lộ. Lúc 10:05:15, registry commit REVOKED. Lúc 10:05:20, gateway B mất kết nối với event bus và còn snapshot K7=ACTIVE.

Hãy tự trả lời:

1. Nếu gateway B chỉ dựa vào TTL cache, request ký K7 lúc 10:05:30 có thể được chấp nhận không? Tại sao?
2. Muốn bảo đảm request mới sau commit đều bị từ chối, B cần kiểm tra thêm gì hoặc áp dụng chính sách nào khi mất kết nối?
3. Nếu K8 đã ACTIVE nhưng đối tác chưa thể cập nhật, có được giữ K7 ACTIVE tạm thời không?
4. Thông tin vận hành tối thiểu cần lưu để chứng minh thu hồi đã có hiệu lực ở A, B và C là gì?
5. HMAC hợp lệ bằng K8 có đủ để gọi một API nhạy cảm không?

**Đáp án định hướng:** (1) Có thể được chấp nhận nếu B tin cache cũ. (2) B phải xác minh freshness ở nguồn thẩm quyền/điểm kiểm soát thu hồi hoặc fail closed khi không chứng minh được. (3) Không nên giữ K7 đã bị lộ để phục vụ tương thích; dùng kênh phục hồi độc lập và chấp nhận gián đoạn có kiểm soát. (4) Lưu thời điểm commit, revision, event/ack của verifier, kết quả kiểm tra theo vùng, correlation ID và các request K7 còn xuất hiện. (5) Chưa đủ: còn timestamp/nonce, trạng thái credential và quyết định phân quyền nghiệp vụ.

Rotation khẩn cấp chỉ thực sự hoàn tất khi **secret mất tin cậy không còn được điểm xác thực nào chấp nhận theo cam kết bảo mật của hệ thống**, secret mới được cấp qua kênh tin cậy, client hợp lệ đã có đường phục hồi và toàn bộ quyết định thu hồi được kiểm chứng bằng dữ liệu vận hành. Việc thay key ID hoặc cập nhật cấu hình client chỉ là một phần trong quy trình đó.
