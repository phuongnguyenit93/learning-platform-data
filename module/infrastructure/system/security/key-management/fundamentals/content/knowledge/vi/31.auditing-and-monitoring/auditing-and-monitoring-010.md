# Unexpected region access

Unexpected region access là tình huống một thao tác liên quan đến khóa mật mã xuất hiện từ vùng (region) không phù hợp với mô hình triển khai, danh tính workload, chính sách dữ liệu hoặc lịch vận hành đã được phê duyệt. Ví dụ, một workload chỉ chạy tại Singapore nhưng có yêu cầu Decrypt từ endpoint ở một region khác; một key thuộc môi trường production bị gọi từ region development; hoặc một principal truy cập key trong vùng chưa được tổ chức cho phép.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, phát hiện truy cập từ region bất thường là một phần của audit và monitoring vòng đời khóa. Tín hiệu này có thể chỉ ra credential bị lộ, workload bị xâm nhập, policy bị thay đổi hoặc cấu hình định tuyến sai. Tuy nhiên, region khác thường không tự động chứng minh có tấn công: multi-region key, failover, dịch vụ toàn cục, NAT, proxy và luồng backup hợp lệ đều có thể tạo ra khác biệt về region. Cần kết hợp region với principal, action, key resource, network source, thời điểm và ngữ cảnh nghiệp vụ.

## 1. Unexpected region access là gì?

Một key access event có thể được xem là bất thường khi region quan sát được khác với vùng được mong đợi cho principal, key hoặc thao tác đó. Region có thể chỉ nhiều khái niệm khác nhau:

- **Request region:** region của endpoint KMS/HSM hoặc dịch vụ nhận API request.
- **Key region:** region nơi key được tạo, quản lý hoặc có bản sao/replica.
- **Workload region:** region nơi ứng dụng, máy ảo, pod hoặc job đang chạy.
- **Source region:** vùng địa lý được suy ra từ địa chỉ IP hoặc network egress của request.
- **Data residency region:** vùng mà dữ liệu được phép lưu trữ hoặc xử lý theo policy.

Các vùng này không nhất thiết trùng nhau. Một ứng dụng ở region A có thể gọi KMS endpoint ở region B theo kiến trúc được phê duyệt; một global endpoint có thể định tuyến tới dịch vụ khu vực; một multi-region key có thể có replica ở nhiều nơi. Do đó, sự kiện cần ghi rõ đang nói đến region nào.

Ví dụ, workload thanh toán chạy ở region Singapore gọi key production qua endpoint Singapore là hành vi bình thường theo baseline. Nếu cùng principal đột ngột gọi Decrypt qua endpoint ở một region không nằm trong danh sách cho phép, sự kiện cần được điều tra. Nếu kiến trúc đã cấu hình DR ở region đó và có change request hợp lệ, cùng hành vi có thể là hoạt động được phê duyệt.

## 2. Vì sao truy cập key từ region bất thường đáng quan tâm?

Kẻ tấn công có credential của workload hoặc quyền IAM có thể thử sử dụng KMS từ môi trường khác để giải mã data key, ký dữ liệu hoặc truy cập key resource ngoài phạm vi dự kiến. Một yêu cầu từ region lạ có thể là dấu hiệu đầu tiên cho thấy credential đã bị sao chép hoặc workload đã bị điều khiển từ nơi khác.

Monitoring region access hỗ trợ:

- Phát hiện credential hoặc machine identity bị sử dụng ngoài môi trường thông thường.
- Phát hiện policy quá rộng cho phép workload truy cập key từ region không được phê duyệt.
- Phát hiện thay đổi kiến trúc, failover hoặc triển khai ngoài kế hoạch.
- Kiểm tra yêu cầu data residency và ranh giới xử lý dữ liệu.
- Phát hiện thao tác nhạy cảm như Decrypt, Sign, GenerateDataKey hoặc thay đổi key policy từ nguồn bất thường.
- Hỗ trợ điều tra bằng cách liên kết region với actor, key, action, source IP và change record.

Một lần truy cập bất thường có thể ảnh hưởng nghiêm trọng hơn nếu liên quan đến key production, dữ liệu nhạy cảm hoặc thao tác có thể tiết lộ plaintext. Mức độ ưu tiên phải xét loại key và action, không chỉ dựa vào tên region.

## 3. Các nguyên nhân hợp lệ và nguyên nhân đáng ngờ

| Tình huống | Có thể hợp lệ khi | Dấu hiệu cần điều tra |
|---|---|---|
| Disaster recovery/failover | Region dự phòng đã được cấu hình, phê duyệt và kiểm thử | Failover không có change/incident record hoặc principal lạ thực hiện |
| Multi-region key | Key replica và quyền truy cập liên vùng được thiết kế rõ | Request tới region không có replica hoặc không thuộc policy |
| Global endpoint/service routing | Tài liệu dịch vụ xác nhận endpoint định tuyến qua region khác | Region thực tế không phù hợp với cấu hình hoặc xuất hiện đột ngột |
| NAT/proxy/VPN | Egress IP hợp lệ được tổ chức quản lý | IP mới, proxy lạ hoặc đường egress không được kiểm soát |
| Backup/restore | Job backup/restore chạy trong cửa sổ được phê duyệt | Job ngoài lịch, principal không đúng hoặc đọc key quá phạm vi |
| Cloud provider maintenance | Có thông báo và event vận hành xác thực | Không có thông báo hoặc đi kèm thay đổi quyền bất thường |
| Credential bị lộ | Không phải hoạt động hợp lệ nếu không có phê duyệt | Cùng credential được dùng từ nhiều region hoặc thiết bị khác nhau |

Không nên tự động allowlist một region chỉ vì nó từng xuất hiện. Mỗi ngoại lệ cần có owner, mục đích, principal, key resource, action và thời hạn rõ ràng.

## 4. Dữ liệu cần thu thập từ key access event

Để phân tích region access, audit event nên cung cấp đủ ngữ cảnh:

| Trường | Ý nghĩa |
|---|---|
| Event ID và timestamp | Định danh sự kiện và thời điểm phát sinh |
| Principal/workload identity | Danh tính đã được xác thực khi gọi dịch vụ |
| Action | Encrypt, Decrypt, GenerateDataKey, Sign, GetPublicKey hoặc thay đổi policy |
| Key ID và key version | Tài nguyên khóa được truy cập |
| Request region | Region của endpoint xử lý request |
| Key region/replica | Region quản lý key hoặc replica liên quan |
| Source IP/network | IP, VPC endpoint, subnet, gateway hoặc network path đã quan sát |
| Workload metadata | Cluster, namespace, service account, instance hoặc job identity |
| Result | Thành công, bị từ chối hoặc lỗi |
| User agent/client | SDK, service hoặc client version nếu có |
| Correlation/change ID | Liên kết với deployment, failover, incident hoặc change request |

Không phải provider nào cũng cung cấp tất cả trường. Cần lưu raw audit record theo quyền truy cập phù hợp, sau đó chuẩn hóa các trường có sẵn. Không suy diễn key region từ source IP hoặc workload region từ tên principal.

## 5. Xây dựng baseline region theo principal và key

Baseline mô tả vùng và đường truy cập bình thường cho từng workload, key và loại thao tác. Một baseline hữu ích không chỉ nói “dịch vụ này ở region X”, mà còn ghi rõ các trường hợp dự phòng.

Ví dụ:

| Principal | Key/resource | Action | Region dự kiến | Ngoại lệ |
|---|---|---|---|---|
| payment-api-prod | payment-data-key | GenerateDataKey, Decrypt | Singapore | DR region chỉ trong incident đã phê duyệt |
| invoice-signing-prod | invoice-signing-key | Sign | Singapore | Không cho phép từ region khác |
| backup-worker-prod | backup-wrapping-key | Encrypt, Decrypt | Singapore | Region DR trong cửa sổ backup/restore |
| reporting-job-stage | reporting-stage-key | Decrypt | Staging region | Không được truy cập production key |

Baseline nên được xây dựng từ:

- Kiến trúc triển khai và sơ đồ luồng dữ liệu đã phê duyệt.
- Key inventory, key policy và danh sách replica/region được hỗ trợ.
- Workload identity và nơi workload được phép chạy.
- Network egress, VPC endpoint, NAT gateway và proxy được quản lý.
- Lịch backup, restore, rotation, deployment và DR test.
- Audit log thực tế trong một khoảng thời gian đủ đại diện.

Không học baseline một cách tự động từ mọi hành vi quan sát được. Nếu attacker đã có quyền và tạo ra hành vi bất thường, việc tự động thêm region đó vào baseline sẽ biến hành vi tấn công thành “bình thường”. Thay đổi baseline phải có review và change record.

## 6. Phát hiện truy cập bất thường bằng nhiều tín hiệu

Region là một tín hiệu, không phải bằng chứng độc lập. Detection rule nên kết hợp nhiều thuộc tính:

- Principal có đúng workload identity và audience/subject mong đợi không?
- Action có nằm trong quyền của workload không?
- Key resource có thuộc môi trường, tenant và data domain của workload không?
- Request region có nằm trong allowlist cho principal và key không?
- Source IP, VPC endpoint hoặc network egress có đúng không?
- Thời điểm có nằm trong lịch triển khai, backup hoặc DR không?
- Có thay đổi policy, grant hoặc credential ngay trước đó không?
- Có tăng đột biến số lần Decrypt/Sign hoặc số key khác nhau được truy cập không?

Một ví dụ rule khái niệm:

~~~text
IF
  action IN (Decrypt, Sign, GenerateDataKey)
  AND request_region NOT IN approved_regions(principal, key, action)
  AND NOT has_valid_change_or_dr_window(event)
THEN
  create_alert("UnexpectedRegionKeyAccess")
  severity = risk_score(principal, key, action, source, context)
~~~

Rule phải tra cứu allowlist theo cặp principal-key-action hoặc policy tương đương. Một workload được phép dùng key A tại region Singapore không có nghĩa nó được phép dùng key B tại cùng region, hoặc dùng key A từ mọi region.

## 7. Đánh giá độ tin cậy của vị trí mạng

Địa chỉ IP có thể cung cấp gợi ý về vị trí, nhưng geolocation không phải bằng chứng chính xác về nơi workload hoặc dữ liệu đang được xử lý. IP có thể thuộc NAT gateway, VPN, proxy, cloud egress hoặc dịch vụ trung gian. Cơ sở dữ liệu geolocation cũng có thể lỗi thời.

Thứ tự ưu tiên khi xác định nguồn truy cập nên dựa trên metadata có độ tin cậy cao:

1. Region endpoint và resource được ghi bởi control plane của KMS.
2. Workload identity và metadata do cloud/container platform xác thực.
3. VPC endpoint, private link, subnet hoặc network route do tổ chức quản lý.
4. Source IP và ASN đã đối chiếu với danh sách egress được quản lý.
5. Geolocation IP như tín hiệu bổ sung, không phải kết luận duy nhất.

Nếu request đi qua proxy, cần ghi nhận cả nguồn gốc workload đã xác thực và egress proxy. Không tin header X-Forwarded-For nếu nó không được một proxy tin cậy ghi đè và bảo vệ.

## 8. Chính sách region và data residency

Tổ chức có thể giới hạn key access theo region vì lý do bảo mật, pháp lý, hợp đồng hoặc yêu cầu data residency. Policy nên xác định rõ:

- Key nào được dùng trong region nào.
- Workload/principal nào được phép gọi key từ region nào.
- Action nào được phép theo từng region.
- Có cho phép cross-region replication hoặc failover không.
- Dữ liệu plaintext, ciphertext, data key và metadata có thể được xử lý/lưu ở đâu.
- Ngoại lệ cần ai phê duyệt, có hiệu lực trong bao lâu và cách thu hồi.

Region của KMS endpoint không nhất thiết cho biết toàn bộ dữ liệu được lưu hoặc xử lý ở region đó. Ví dụ, thao tác giải mã data key có thể trả plaintext data key về workload ở region khác; điều này có thể ảnh hưởng yêu cầu residency dù key material vẫn được bảo vệ trong KMS. Cần đánh giá cả nơi plaintext được tạo, sử dụng, cache và lưu trữ.

Không coi region restriction là thay thế cho encryption, IAM policy, network control hoặc phân quyền theo tenant. Các lớp này cần phối hợp để tạo ranh giới bảo vệ.

## 9. Multi-region key và failover

Một số hệ thống hỗ trợ multi-region key hoặc replica key để tăng availability và hỗ trợ DR. Trong trường hợp này, truy cập từ nhiều region có thể là thiết kế hợp lệ. Tuy nhiên, phải xác định rõ:

- Region chính và các region replica được phép.
- Cách đồng bộ key metadata, policy và trạng thái disable/revoke.
- Principal nào được phép dùng replica tại từng region.
- Dữ liệu và ciphertext nào được phép chuyển vùng.
- Cách xử lý khi một region bị compromise hoặc mất kết nối.
- Quy trình failover, failback và kiểm thử định kỳ.

Không giả định trạng thái policy hoặc revoke lan truyền tức thời giữa các replica. Phải kiểm tra semantics của dịch vụ, độ trễ replication và hành vi khi một region không liên lạc được với control plane.

DR exception nên gắn với change/incident ID, thời gian bắt đầu-kết thúc, owner và phạm vi key/action. Sau khi failover kết thúc, phải thu hồi quyền tạm thời và xác minh workload đã quay lại trạng thái dự kiến.

## 10. Ví dụ phân loại alert

| Sự kiện quan sát | Ngữ cảnh | Mức độ gợi ý | Hành động |
|---|---|---|---|
| Production Decrypt từ region chưa từng dùng | Principal và IP đều lạ, không có DR | Critical/High | Xác minh ngay, cân nhắc chặn principal và điều tra credential |
| Sign từ region khác | Key ký production chỉ được phép tại một region | High | Kiểm tra principal, endpoint, certificate và policy |
| GenerateDataKey từ DR region | Có incident và change window đã phê duyệt | Informational/Low | Ghi nhận ngoại lệ, theo dõi hết hạn |
| Decrypt từ IP mới nhưng request region đúng | Workload vừa chuyển NAT gateway | Medium | Đối chiếu network change và workload identity |
| Truy cập staging key từ production principal | Region giống nhau nhưng môi trường sai | High | Kiểm tra policy và quyền cross-environment |
| Tăng mạnh Decrypt từ region hợp lệ | Principal hợp lệ nhưng volume bất thường | High | Kiểm tra khả năng credential bị lạm dụng hoặc ứng dụng lỗi |

Mức độ cuối cùng phải theo hệ thống phân loại rủi ro của tổ chức. Một request bị từ chối từ region lạ có thể là probe hoặc cấu hình sai; một request Decrypt thành công từ principal bị xâm nhập có thể cần phản ứng khẩn cấp.

## 11. Quy trình điều tra alert unexpected region access

Khi nhận cảnh báo:

1. Xác minh event đến từ audit source đáng tin cậy; kiểm tra event ID, request ID và timestamp.
2. Xác định request region, key region, workload region và source network riêng biệt.
3. Kiểm tra principal, credential type, action, key ID/version và kết quả thành công/thất bại.
4. Đối chiếu allowlist, key policy, IAM policy, grant và điều kiện context hiện tại.
5. Kiểm tra deployment, DR test, backup, maintenance hoặc change request trong cùng khoảng thời gian.
6. Đối chiếu source IP, VPC endpoint, NAT, proxy và cloud service principal.
7. Tìm các event liên quan trước/sau đó: tạo credential, thay policy, tạo grant, truy cập key khác hoặc tăng volume.
8. Đánh giá dữ liệu có thể bị giải mã, data key có thể đã được trả về và plaintext có thể đã rời workload hay không.
9. Quyết định cho phép ngoại lệ, chặn request, thu hồi credential hoặc hạn chế principal theo mức độ rủi ro.
10. Ghi kết luận, owner, bằng chứng và hành động tiếp theo vào incident/change record.

Không tắt key ngay chỉ vì một alert region đơn lẻ. Vô hiệu hóa key có thể làm gián đoạn nhiều workload và gây mất khả năng giải mã. Cần xác định phạm vi phụ thuộc và cân nhắc chặn principal hoặc region path bị ảnh hưởng trước, trừ khi bằng chứng cho thấy key material đã bị compromise và cần biện pháp khẩn cấp.

## 12. Phản ứng khi xác nhận truy cập trái phép

Nếu xác nhận một principal đã dùng key từ region không được phép:

- Ngăn các yêu cầu mới từ principal hoặc credential bị ảnh hưởng bằng cách revoke token, disable credential, thu hồi grant hoặc cập nhật policy.
- Giới hạn network path hoặc workload bị xâm nhập nếu cần.
- Xem xét session/token cache và độ trễ policy propagation.
- Kiểm tra các thao tác Decrypt, Sign, GenerateDataKey, Export/Import hoặc thay đổi policy đã xảy ra.
- Xác định plaintext data key hoặc plaintext có thể đã được trả về workload.
- Nếu key material hoặc data key bị lộ, đánh giá key rotation, re-wrapping hoặc re-encryption.
- Nếu chỉ có quyền truy cập bất thường nhưng chưa có bằng chứng lộ key material, thu hồi identity/quyền có thể là biện pháp phù hợp hơn việc destroy key.
- Lưu audit evidence, phối hợp incident response và xác minh các consumer đã áp dụng policy mới.

Thu hồi quyền không xóa plaintext đã bị lấy. Thay key cũng không tự động thu hồi các bản sao plaintext hoặc ciphertext đã bị sao chép. Phải đánh giá riêng phạm vi dữ liệu và thông báo theo quy trình sự cố của tổ chức.

## 13. Tích hợp với audit, SIEM và cảnh báo

Một pipeline monitoring region access thường gồm:

~~~mermaid
flowchart TD
    A[KMS/HSM audit events] --> D[Collector]
    B[Cloud identity/workload events] --> D
    C[Network flow/VPC logs] --> D
    D --> E[Normalize and enrich]
    E --> F[Region baseline and policy]
    F --> G[Detection rules / risk scoring]
    G --> H[SIEM alert]
    G --> I[Case management]
    I --> J[Investigation and response]
    J --> K[Update baseline or policy with approval]
~~~

Các nguồn cần đồng bộ thời gian và giữ correlation ID nếu có. Pipeline nên lưu raw event để đối chiếu với dữ liệu đã enrich. Việc enrich bằng geolocation hoặc inventory cần ghi nguồn và thời điểm dữ liệu được tra cứu để tránh coi metadata suy luận là dữ kiện gốc.

Các chỉ số nên theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Key requests by request region | Phân bố thao tác key theo region endpoint |
| Unexpected region events | Số event không khớp baseline/policy |
| Successful unexpected Decrypt/Sign | Số thao tác nhạy cảm thành công từ region bất thường |
| Region policy denials | Số request bị policy từ chối |
| New principal-region pairs | Principal xuất hiện lần đầu tại một region |
| Mean time to detect/respond | Thời gian phát hiện và phản ứng |
| DR exception expiry | Ngoại lệ region sắp hết hạn hoặc quá hạn |

Alert cần có owner, mức độ, key/principal liên quan, lý do rule kích hoạt và liên kết tới audit event. Tránh đưa secret, token hoặc plaintext key material vào SIEM.

## 14. Quản lý ngoại lệ và giảm false positive

Ngoại lệ region nên được quản lý như một quyền có thời hạn:

- Gắn với principal, key/resource và action cụ thể.
- Ghi lý do, change/incident ID, người phê duyệt và owner.
- Xác định region nguồn/đích và network path được phép.
- Đặt thời điểm bắt đầu và hết hạn.
- Theo dõi số lần sử dụng và phát cảnh báo nếu vượt dự kiến.
- Tự động hoặc thủ công thu hồi sau khi hết hạn.
- Rà soát lại sau mỗi DR test hoặc thay đổi kiến trúc.

False positive thường đến từ NAT/proxy mới, SDK dùng global endpoint, thay đổi route, DR test hoặc replica key mới. Để giảm cảnh báo sai, hãy enrich event bằng inventory và change management, nhưng không tự động đưa hành vi mới vào allowlist. Mọi cập nhật baseline cần review, bằng chứng và chủ sở hữu.

## 15. Rủi ro và lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Coi IP geolocation là vị trí workload chính xác | Tạo cảnh báo sai hoặc bỏ sót proxy/NAT | Kết hợp request region, workload identity và network metadata tin cậy |
| Không phân biệt request region với key region | Đánh giá nhầm multi-region access | Ghi riêng từng loại region trong event |
| Allowlist cả region cho mọi principal | Mở rộng quyền ngoài nhu cầu | Allowlist theo principal, key, action và thời hạn |
| Tự động học mọi region mới thành baseline | Hành vi tấn công có thể trở thành bình thường | Yêu cầu review và change approval |
| Bỏ qua DR và replica semantics | Chặn nhầm hoạt động hợp lệ hoặc bỏ lỡ lỗi propagation | Kiểm tra cấu hình replica, failover và policy thực tế |
| Chỉ theo dõi request bị từ chối | Bỏ sót thao tác bất thường đã thành công | Alert riêng cho Decrypt/Sign thành công từ nguồn lạ |
| Tắt key ngay khi có một alert | Có thể gây gián đoạn và mất khả năng giải mã | Xác minh phạm vi, chặn principal/path trước khi quyết định |
| Không theo dõi ngoại lệ hết hạn | Quyền cross-region tạm thời tồn tại lâu dài | Đặt owner, TTL và cảnh báo expiry |
| Không tương quan với policy change | Bỏ lỡ việc attacker mở rộng quyền trước khi truy cập | Theo dõi grant, IAM/key policy và credential events |
| Ghi secret vào log điều tra | Tạo thêm nơi rò rỉ credential/key material | Chỉ lưu reference và metadata không bí mật |

## 16. Checklist triển khai

- [ ] Định nghĩa rõ request region, key region, workload region, source region và data residency.
- [ ] Ghi region cùng principal, action, key ID/version, source network và kết quả request.
- [ ] Xây dựng baseline theo principal-key-action và môi trường.
- [ ] Xác minh nguồn metadata region; không chỉ dựa vào geolocation IP.
- [ ] Kết hợp region với identity, network, volume, thời điểm và policy change.
- [ ] Xác định allowlist và ngoại lệ cho multi-region key, backup và DR.
- [ ] Mỗi ngoại lệ có owner, approval, scope và thời hạn.
- [ ] Cảnh báo riêng cho Decrypt/Sign thành công từ region không mong đợi.
- [ ] Theo dõi request bị từ chối, policy change và credential mới cùng thời điểm.
- [ ] Có quy trình điều tra và thu hồi principal/credential khi xác nhận truy cập trái phép.
- [ ] Đánh giá plaintext data key và dữ liệu có thể đã bị lộ trước khi quyết định re-encrypt.
- [ ] Kiểm thử failover, cache, replica và policy propagation.
- [ ] Lưu raw audit event, detection result và incident evidence có kiểm soát truy cập.

Unexpected region access là tín hiệu quan trọng để phát hiện việc sử dụng key ngoài ranh giới dự kiến, nhưng chỉ có ý nghĩa khi region được định nghĩa rõ và phân tích cùng danh tính, action, key resource, network path và change context. Monitoring tốt giúp phân biệt failover hợp lệ với credential bị lạm dụng, phản ứng đúng mức và duy trì bằng chứng audit đáng tin cậy.
