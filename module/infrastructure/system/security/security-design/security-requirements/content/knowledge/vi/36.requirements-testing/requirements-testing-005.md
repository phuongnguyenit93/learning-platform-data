# Abuse case test: kiểm thử kịch bản lạm dụng

## 1. Mục tiêu bài học

**Abuse case test** là ca kiểm thử xuất phát từ một mục tiêu lạm dụng hệ thống: một chủ thể cố đạt kết quả mà chính sách bảo mật hoặc quy tắc nghiệp vụ không cho phép. Ca kiểm thử mô tả khả năng của chủ thể, điều kiện ban đầu, chuỗi hành động và bằng chứng để xác định hệ thống đã ngăn chặn, phát hiện hoặc giới hạn hậu quả theo yêu cầu hay chưa.

Trong thiết kế yêu cầu bảo mật, abuse case test nối mô hình đe dọa với hành vi có thể kiểm chứng. Nó giúp trả lời:

> Với khả năng và đường truy cập đã xác định, chủ thể có đạt được mục tiêu trái phép không, và các yêu cầu bảo vệ liên quan có thực sự có hiệu lực không?

Học xong bài này, bạn có thể:

- Chuyển kịch bản đe dọa thành ca kiểm thử có tiền điều kiện và tiêu chí đạt rõ ràng.
- Kiểm tra lạm dụng bằng tài khoản hợp lệ, tài nguyên đúng định dạng và chuỗi thao tác qua nhiều thành phần.
- Xây dựng oracle, tức căn cứ để kết luận kết quả đúng hay sai, ngoài mã phản hồi.
- Kiểm tra tác dụng phụ, tác vụ nền, thu hồi quyền và hành vi đồng thời.
- Liên kết yêu cầu, abuse case, kết quả và bằng chứng theo phiên bản.

Mã yêu cầu, endpoint, trạng thái và ngưỡng số trong bài là ví dụ của một hệ thống giả định. Các ca được thiết kế cho môi trường kiểm thử do nhóm quản lý, dùng danh tính và dữ liệu tổng hợp.

## 2. Abuse case test khác gì một ca nhập sai dữ liệu?

Một tài khoản hợp lệ vẫn có thể lạm dụng chức năng. Đầu vào cũng có thể đúng schema, chữ ký token hợp lệ và thao tác được gọi qua API chính thức.

Ví dụ:

> Người dùng tenant A có quyền xuất hồ sơ của tenant A, nhưng thay mã tài nguyên để xuất hồ sơ của tenant B.

Chuỗi này không nhất thiết chứa dữ liệu sai định dạng. Điểm cần kiểm chứng là quyết định cấp quyền trên tài nguyên và tenant đích.

### 2.1. Các loại kiểm thử liên quan

| Loại | Điểm xuất phát | Ví dụ |
|---|---|---|
| Ca nghiệp vụ hợp lệ | Người dùng làm việc theo quyền và quy tắc | Xuất hồ sơ của tenant mình khi có quyền. |
| Kiểm thử âm tính | Điều kiện không hợp lệ hoặc không được phép | Thiếu trường bắt buộc, token hết hạn hoặc không có vai trò cần thiết. |
| Abuse case test | Chủ thể cố đạt một mục tiêu trái phép | Dùng quyền hợp lệ để yêu cầu tài nguyên tenant khác qua API và worker. |
| Kiểm thử xâm nhập | Hoạt động đánh giá có phạm vi, có thể kết hợp nhiều kỹ thuật và chuỗi phát hiện | Khảo sát đường đi để vượt kiểm soát, sau đó khai thác có kiểm soát trong phạm vi được giao. |
| Kiểm thử hồi quy bảo mật | Giữ một thuộc tính bảo vệ đã được xác nhận | Chạy lại ca chéo tenant khi cơ chế phân quyền thay đổi. |

Các nhóm có thể dùng thuật ngữ hơi khác nhau. Một abuse case có thể tạo ra nhiều ca âm tính và sau đó trở thành bộ kiểm thử hồi quy. Điều quan trọng là giữ rõ mục tiêu lạm dụng, khả năng chủ thể và kết quả bảo vệ cần chứng minh.

### 2.2. Cần có ca hợp lệ để đối chứng

Nếu mọi yêu cầu đều trả lỗi do dịch vụ chưa khởi động, ca lạm dụng cũng có thể bị “chặn”. Đó không phải bằng chứng phân quyền hoạt động.

Trước hoặc cùng với ca lạm dụng, cần chứng minh:

- Dịch vụ và đường gọi đang hoạt động.
- Danh tính của chủ thể được xác thực đúng.
- Chức năng hợp lệ trong phạm vi được phép vẫn thành công.
- Tài nguyên đích trong fixture thực sự tồn tại.

Ca đối chứng giúp phân biệt từ chối đúng chính sách với lỗi môi trường, sai endpoint hoặc dữ liệu thử chưa được tạo.

## 3. Đi từ rủi ro tới yêu cầu và ca kiểm thử

Một cách tổ chức chuỗi truy vết:

```text
Tài sản + ranh giới tin cậy + chủ thể
                   |
                   v
          Mục tiêu lạm dụng
                   |
                   v
       Kịch bản đe dọa / rủi ro
                   |
                   v
       Yêu cầu bảo mật cần đáp ứng
                   |
                   v
       Abuse case và biến thể kiểm thử
                   |
                   v
   Oracle + kết quả + bằng chứng theo phiên bản
```

Ví dụ:

| Thành phần | Nội dung |
|---|---|
| Tài sản | Hồ sơ riêng của từng tenant và tệp xuất được tạo từ hồ sơ. |
| Chủ thể | Người dùng hợp lệ của tenant A, có quyền xuất trong tenant A. |
| Mục tiêu lạm dụng | Đọc hoặc tải dữ liệu thuộc tenant B. |
| Đường lạm dụng | Gửi mã tài nguyên hoặc tenant khác qua API xuất dữ liệu; thử đường tải tệp. |
| Rủi ro | Mất tính bí mật giữa các tenant. |
| Yêu cầu | Mọi điểm truy cập dữ liệu phải kiểm tra quyền theo chủ thể, hành động, tenant và tài nguyên. |
| Ca kiểm thử | Gọi API trực tiếp bằng danh tính A để xuất tài nguyên B. |
| Kết quả cần có | Từ chối theo hợp đồng API, không tạo kết quả trái phép, không làm lộ dữ liệu và có audit theo yêu cầu. |

Không dừng ở “đầu vào nguy hiểm bị chặn”. Cần chỉ ra thuộc tính bảo vệ nào được giữ và bằng chứng nào cho thấy điều đó.

## 4. Cấu trúc của một abuse case test

Một ca đủ rõ nên có các phần:

| Trường | Câu hỏi cần trả lời |
|---|---|
| Mã và phiên bản ca | Ca nào đang được chạy, nội dung thuộc phiên bản nào? |
| Yêu cầu và rủi ro liên quan | Đang kiểm chứng điều gì và vì sao cần kiểm chứng? |
| Tài sản và phạm vi | Dữ liệu, chức năng, dịch vụ và môi trường nào được xét? |
| Chủ thể và khả năng | Có tài khoản gì, quyền gì, biết thông tin gì và tiếp cận được đường nào? |
| Tiền điều kiện | Dữ liệu, trạng thái quyền, tác vụ và cấu hình nào phải tồn tại? |
| Mục tiêu lạm dụng | Kết quả trái phép mà chủ thể muốn đạt là gì? |
| Chuỗi hành động | Gửi yêu cầu nào, theo thứ tự nào, tại thời điểm nào? |
| Oracle | Quan sát nào đủ để kết luận đạt hoặc trượt? |
| Giới hạn quan sát | Khi nào chuỗi xử lý liên quan được coi là kết thúc và bằng chứng được xem là đầy đủ? |
| Bằng chứng | Phản hồi, trạng thái dữ liệu, sự kiện, cấu hình và phiên bản nào cần lưu? |
| Dọn dữ liệu | Xóa đúng fixture hoặc kết quả do ca tạo ra như thế nào? |

### 4.1. Khả năng của chủ thể phải thực tế

Nếu giả định chủ thể có quyền quản trị cơ sở dữ liệu, ca kiểm thử không còn kiểm chứng cùng ranh giới với người dùng chỉ có quyền gọi API.

Ví dụ với tenant isolation:

- Chủ thể có token hợp lệ của tenant A.
- Chủ thể có thể gọi API trực tiếp, không cần dùng giao diện.
- Chủ thể biết mã tài nguyên B do fixture cung cấp để kiểm tra thuộc tính phân quyền.
- Chủ thể không có quyền sửa cơ sở dữ liệu hoặc chính sách phía máy chủ.
- Quyền quan sát nội bộ của test harness được tách khỏi quyền của chủ thể.

Việc fixture cung cấp mã tài nguyên B giúp ca tập trung vào kiểm tra quyền, không có nghĩa sản phẩm được phép dựa vào mã khó đoán để bảo vệ dữ liệu.

### 4.2. Tách mục tiêu lạm dụng khỏi kỹ thuật thử

“Đổi documentId” là một hành động. “Đọc tài liệu không được phép” mới là mục tiêu.

Một mục tiêu có thể có nhiều đường: endpoint trực tiếp, worker, liên kết tải hoặc thao tác hàng loạt. Nếu chỉ giữ một chuỗi thao tác mà không giữ mục tiêu, nhóm có thể sửa một đường và bỏ sót đường khác.

## 5. Xây dựng oracle: đừng chỉ kiểm tra HTTP status

Oracle là tập căn cứ xác định hành vi quan sát được có đáp ứng yêu cầu không.

Một phản hồi 403 hoặc 404 có thể vẫn đi kèm tác dụng phụ trái phép: tác vụ đã được ghi vào hàng đợi, tệp đã được tạo hoặc dữ liệu đã thay đổi trước khi phản hồi lỗi được trả về.

### 5.1. Những lớp quan sát thường cần có

| Lớp | Ví dụ điều cần kiểm tra |
|---|---|
| Phản hồi cho chủ thể | Mã và nội dung đúng hợp đồng; không có dữ liệu hoặc liên kết trái phép. |
| Trạng thái nghiệp vụ | Không sửa hoặc xóa tài nguyên ngoài quyền; không tạo tác vụ trái phép. |
| Xử lý bất đồng bộ | Không để worker tạo kết quả từ một yêu cầu đã bị từ chối. |
| Tệp và quyền tải | Không tạo hoặc công bố tệp cho chủ thể không được phép; không có đường tải đi vòng. |
| Audit và giám sát | Có sự kiện theo yêu cầu, liên kết được với thao tác và không chứa bí mật. |
| Tác động cho người dùng hợp lệ | Chức năng được phép vẫn hoạt động đúng trong phạm vi đối chứng. |

Không phải ca nào cũng cần tất cả lớp. Chọn theo yêu cầu và luồng thực tế, ghi rõ phần nào không được kiểm chứng.

### 5.2. Phân biệt tác dụng phụ trái phép với tác dụng phụ được yêu cầu

Một yêu cầu bị từ chối vẫn có thể tạo sự kiện audit hoặc tăng bộ đếm giới hạn truy cập. Vì vậy, “không có bất kỳ thay đổi nào” thường không phải oracle chính xác.

Cần quy định cụ thể:

- Không có tác vụ xuất được chấp nhận cho tài nguyên trái phép.
- Không có tệp hoặc quyền tải mới chứa dữ liệu đó.
- Tài nguyên nghiệp vụ không bị thay đổi.
- Sự kiện từ chối vẫn được ghi theo chính sách.

### 5.3. Mã lỗi phải được đặc tả trước

Một API có thể chọn 404 để không tiết lộ sự tồn tại của tài nguyên ngoài tenant. Một API khác có thể dùng 403 theo hợp đồng của nó.

Ca kiểm thử cần bám vào hợp đồng đã xác định. Không chấp nhận mọi mã 4xx rồi kết luận an toàn: 400 do sai schema hoặc 401 do token hỏng chưa chứng minh kiểm tra quyền trên tài nguyên.

Với 404, cần ca đối chứng và fixture xác nhận endpoint cùng tài nguyên thực sự tồn tại, tránh “đạt” vì gọi nhầm đường dẫn.

## 6. Ví dụ đầy đủ: xuất dữ liệu chéo tenant

### 6.1. Các yêu cầu liên quan

Dịch vụ giả định có các yêu cầu:

- **SEC-EXP-01:** Chỉ cho phép xuất tài nguyên khi chủ thể có quyền cho hành động và tenant sở hữu tài nguyên.
- **SEC-EXP-02:** Yêu cầu xuất bị từ chối không được tạo tác vụ được chấp nhận, tệp xuất hoặc quyền tải trái phép.
- **SEC-EXP-03:** Ghi audit cho yêu cầu xuất bị từ chối với chủ thể, tenant của chủ thể, hành động, kết quả và mã tương quan; không ghi token hay nội dung hồ sơ.
- **SEC-EXP-04:** Quyền bị thu hồi phải được phản ánh trong giới hạn thời gian đã quy định tại các điểm thực thi liên quan.
- **SEC-EXP-05:** Mỗi cặp chủ thể–tenant có tối đa hai tác vụ xuất đang ở trạng thái QUEUED hoặc RUNNING.

Giới hạn hai tác vụ và các tham số thời gian ở phần sau chỉ dùng để minh họa cách đặc tả.

### 6.2. Fixture

| Đối tượng | Trạng thái |
|---|---|
| user-a | Thuộc tenant-a, có quyền xuất hồ sơ trong tenant-a. |
| user-b | Thuộc tenant-b, có quyền xuất hồ sơ trong tenant-b. |
| doc-a-001 | Thuộc tenant-a, có dữ liệu tổng hợp nhận diện riêng. |
| doc-b-001 | Thuộc tenant-b, có dữ liệu tổng hợp khác. |
| observer | Danh tính của test harness để đọc trạng thái kiểm thử và bằng chứng theo phạm vi được cấp. |

Client thực hiện hành động lạm dụng phải dùng user-a. Observer chỉ quan sát và kiểm tra fixture, không được vô tình dùng làm danh tính gọi yêu cầu lạm dụng.

Trước ca chính, xác minh user-a xuất được doc-a-001 và luồng hoàn tất đúng. Dọn hoặc tách kết quả đối chứng để không nhầm với kết quả của ca lạm dụng.

### 6.3. Hành động lạm dụng

Chủ thể user-a gửi yêu cầu bằng thông tin xác thực hợp lệ của chính mình:

```http
POST /v1/tenants/tenant-b/export-jobs
Content-Type: application/json
Authorization: Bearer <token-fixture-user-a>

{
  "documentIds": ["doc-b-001"]
}
```

Chuỗi token trong ví dụ là ký hiệu, không phải bí mật thực. Ca không sửa token thành token lỗi, vì mục tiêu là kiểm tra phân quyền sau khi xác thực đã thành công.

### 6.4. Kết quả kỳ vọng

Hợp đồng API giả định chọn 404 cho truy cập tài nguyên ngoài tenant:

1. Phản hồi là 404 theo hợp đồng, không có nội dung hồ sơ, mã tác vụ được chấp nhận hoặc liên kết tải.
2. Không có tác vụ xuất được chấp nhận cho yêu cầu này trong kho trạng thái và hàng đợi liên quan.
3. Không có tệp hoặc quyền tải mới chứa dữ liệu B được tạo cho user-a.
4. Hồ sơ B và các quyền của nó không bị thay đổi.
5. Có sự kiện audit từ chối đúng chủ thể và mã tương quan.
6. Sự kiện không chứa token, liên kết bí mật hoặc nội dung hồ sơ.
7. Ca đối chứng hợp lệ vẫn thành công.

Đối với hệ thống bất đồng bộ, việc kiểm tra không có kết quả trái phép phải dựa trên điểm hoàn tất luồng và cách quan sát được xác định, không chỉ chụp trạng thái ngay sau phản hồi HTTP.

### 6.5. Đặc tả ca ở dạng có cấu trúc

```yaml
case_id: AB-EXP-01
case_revision: rev-1
risk_ref: RISK-CROSS-TENANT-EXPORT
requirement_refs:
  - SEC-EXP-01
  - SEC-EXP-02
  - SEC-EXP-03
actor_fixture: user-a
goal: Đọc dữ liệu tenant-b qua chức năng xuất
preconditions:
  - user-a có quyền xuất trong tenant-a
  - doc-b-001 tồn tại và thuộc tenant-b
  - Ca xuất hợp lệ trong tenant-a đã đạt
action:
  method: POST
  path: /v1/tenants/tenant-b/export-jobs
  document_ids:
    - doc-b-001
expected:
  http_status: 404
  accepted_jobs_for_request: 0
  unauthorized_artifacts_for_actor: 0
  target_business_state: UNCHANGED
  audit_result: DENIED
  sensitive_content_in_response_or_audit: ABSENT
observation:
  - Truy vấn trạng thái có thẩm quyền theo mã tương quan
  - Xác nhận điểm hoàn tất xử lý và không còn công việc liên quan chưa xét
  - Kiểm tra sự kiện audit trong thời hạn yêu cầu đã đặc tả
cleanup: Chỉ xóa dữ liệu và kết quả thuộc fixture của lần chạy
```

Đặc tả này là nội dung minh họa, không phải cấu hình chạy trực tiếp. Trong bộ kiểm thử thực tế cần bổ sung địa chỉ môi trường, phiên bản ứng dụng, phương pháp đồng bộ và cách kiểm tra bằng chứng cụ thể.


## 7. Minh họa logic tự động hóa ca kiểm thử

Đoạn dưới là giả mã độc lập với framework. Các hàm observer biểu diễn khả năng quan sát của test harness, không phải API công khai của sản phẩm.

```text
given:
    fixture = tạo_dữ_liệu_riêng_cho_lần_chạy()
    actorClient = client_xác_thực_bằng(fixture.userA)
    observer = observer_nội_bộ_có_quyền_kiểm_thử()

    xác_nhận(fixture.docB thuộc fixture.tenantB)
    xác_nhận(actorClient xuất fixture.docA thành_công)
    baseline = observer.chụp_trạng_thái_nghiệp_vụ(fixture.docB)

when:
    response = actorClient.tạo_tác_vụ_xuất(
        tenant = fixture.tenantB,
        documentIds = [fixture.docB]
    )
    requestId = lấy_mã_tương_quan_do_hệ_thống_trả_về(response)

then:
    assert response.status == 404
    assert response không_chứa_dữ_liệu_hồ_sơ
    assert response không_chứa_tác_vụ_được_chấp_nhận_hoặc_liên_kết_tải

    observer.đợi_điểm_hoàn_tất_nhân_quả_đã_đặc_tả(requestId)
    assert observer.tác_vụ_được_chấp_nhận(requestId).count == 0
    assert observer.kết_quả_xuất_trái_phép(requestId, fixture.userA).count == 0
    assert observer.trạng_thái_nghiệp_vụ(fixture.docB) == baseline

    audit = observer.đợi_audit(requestId, thời_hạn_từ_yêu_cầu)
    assert audit.actor == fixture.userA
    assert audit.result == DENIED
    assert audit không_chứa_bí_mật_hoặc_nội_dung_hồ_sơ

finally:
    dọn_đúng_dữ_liệu_của_lần_chạy(fixture)
```

Các điểm cần giữ khi hiện thực hóa:

- Hành động lạm dụng dùng actorClient, không dùng observer có quyền cao hơn.
- Quan sát tác vụ và tệp được giới hạn theo lần chạy, chủ thể và mã tương quan, tránh nhầm với ca đối chứng hoặc ca chạy song song.
- Chụp trạng thái nghiệp vụ cần xác định trường nào thuộc tài nguyên cần bảo vệ; sự kiện audit được phép thay đổi.
- Bằng chứng chỉ lưu thông tin cần thiết; token của fixture cũng không cần được ghi nguyên vẹn.
- Dọn dữ liệu không được xóa bằng chứng trước khi thu thập hoặc xóa dữ liệu của lần chạy khác.

Không giả lập sẵn kết quả “DENIED” của chính bộ quyết định quyền rồi dùng nó để khẳng định toàn bộ luồng phân quyền hoạt động. Có thể dùng mô phỏng cho kiểm thử thành phần, nhưng cần kiểm thử tích hợp ở điểm thực thi thực tế.

## 8. Xử lý worker và quan sát kết quả bất đồng bộ

### 8.1. Vì sao sleep cố định thường không đủ?

Giả sử test đợi 500 mili giây rồi không thấy tệp nên kết luận đạt. Worker có thể tạo tệp sau hai giây. Ngược lại, môi trường chậm có thể làm test thất bại dù hệ thống vẫn nằm trong thời hạn được phép.

Cần xác định:

- Điểm hệ thống chấp nhận hoặc từ chối công việc.
- Nơi lưu trạng thái có thẩm quyền.
- Công việc bền vững có thể còn trong hàng đợi hoặc outbox hay không.
- Dấu hiệu hoàn tất hoặc mốc xử lý mà test có thể theo dõi.
- Thời hạn yêu cầu cho xử lý và quan sát audit, nếu có.

Với yêu cầu bị từ chối ngay tại API, một bằng chứng quan trọng là giao dịch hoàn tất mà không có bản ghi tác vụ hoặc thông điệp công việc được chấp nhận. Với tác vụ được chấp nhận nhưng phải bị từ chối ở worker, cần theo dõi tới trạng thái kết thúc tương ứng và kiểm tra kết quả không được công bố.

### 8.2. Quan sát vắng mặt cần có phạm vi

“Không thấy tệp” chỉ có ý nghĩa khi biết đã quan sát đúng kho, đúng mã tác vụ và sau điểm xử lý cần xét.

Có thể kết hợp:

- Trạng thái bền vững của tác vụ.
- Bản ghi công việc liên quan trong hàng đợi hoặc outbox.
- Checkpoint hoặc dấu hoàn tất của worker.
- Danh sách đối tượng đầu ra và quyền tải.
- Sự kiện audit theo mã tương quan.

Nếu đọc qua replica có độ trễ hoặc cache chưa đồng bộ, kết quả “không có” có thể sai. Chọn nguồn đọc và cách chờ phù hợp với độ nhất quán của hệ thống.

Một khoảng quan sát hữu hạn không chứng minh mọi hành vi có thể xảy ra trong tương lai. Kết luận phải gắn với phạm vi và cơ chế hoàn tất đã được xác định.

### 8.3. Timeout không tự trở thành lỗi bảo mật

- Nếu yêu cầu quy định sự kiện phải có trong một thời hạn, môi trường đã được xác nhận hoạt động đúng và sự kiện vẫn không xuất hiện, ca có thể trượt tiêu chí đó.
- Nếu bộ thu bằng chứng bị hỏng hoặc fixture không được tạo, chưa đủ căn cứ kết luận ứng dụng vi phạm kiểm soát.
- Nếu yêu cầu chưa định nghĩa giới hạn xử lý nhưng test tự đặt một timeout ngắn, cần làm rõ đặc tả trước khi dùng timeout làm tiêu chí bảo mật.

Giữ bằng chứng để phân biệt các tình huống. Không chạy lại nhiều lần tới khi xanh rồi bỏ qua các lần thất bại chưa được giải thích.

## 9. Kiểm thử lạm dụng trạng thái và thời điểm

Một abuse case thường là chuỗi có trạng thái, không chỉ một request.

### 9.1. Thu hồi quyền trong lúc tác vụ chờ

Giả sử SEC-EXP-04 quy định quyền bị thu hồi phải có hiệu lực trong tối đa 60 giây tính từ lúc nguồn quyền có thẩm quyền ghi nhận thành công sự kiện. Worker phải kiểm tra trước khi đọc dữ liệu và trước khi công bố kết quả; đường tải kiểm tra lúc bắt đầu một lần tải mới.

Ca AB-EXP-02 có thể gồm:

1. user-a có quyền và tạo tác vụ hợp lệ cho tenant-a.
2. Test giữ worker tại điểm kiểm soát được xác định, trước bước cần kiểm tra quyền.
3. Thu hồi quyền tại nguồn có thẩm quyền, ghi nhận thời điểm t0.
4. Sau mốc phải phản ánh thu hồi, cho worker tiếp tục.
5. Kiểm tra tác vụ không tạo hoặc công bố kết quả trái chính sách.
6. Thử bắt đầu một lần tải mới qua mọi đường thuộc phạm vi.
7. Kiểm tra audit và trạng thái tác vụ.

Cần thêm biến thể thu hồi trong khi worker đang xử lý để kiểm tra điểm trước khi công bố. Tác vụ cũ không được dùng snapshot vai trò làm đường bỏ qua yêu cầu kiểm tra hiện hành.

### 9.2. Đo đúng giới hạn thu hồi

Trong khoảng từ t0 tới trước khi hết giới hạn, hệ thống có thể đã từ chối sớm hoặc vẫn đang đồng bộ theo điều được đặc tả. Không viết test yêu cầu từ chối tức thời nếu đặc tả cho phép độ trễ.

Khi kiểm tra sau giới hạn:

- Liên kết được thời điểm thu hồi với quyết định quyền.
- Xem xét sai lệch đồng hồ hoặc dùng cách đo thời gian phù hợp.
- Kiểm tra các instance, cache và đường truy cập thuộc phạm vi.
- Tách kiểm thử logic với đồng hồ điều khiển khỏi kiểm thử tích hợp đo độ trễ thực tế.

Đồng hồ giả giúp kiểm thử biên thời gian của một thành phần. Nó không chứng minh mạng, đồng bộ dữ liệu và cache thực tế đều đáp ứng cùng giới hạn.

### 9.3. Liên kết tải đã phát hành

Nếu liên kết tự mang quyền truy cập và không hỏi lại nguồn quyền, việc kiểm tra lúc tạo tác vụ có thể không bảo vệ lần tải sau khi quyền bị thu hồi.

Ca kiểm thử cần dùng liên kết cũ trong điều kiện đã xác định, kiểm tra cả đường tải trực tiếp và đường tải qua ứng dụng. Không coi việc ẩn nút tải là đủ.

Phải nêu rõ phạm vi yêu cầu: từ chối lần tải mới sau giới hạn khác với dừng một luồng tải đã bắt đầu hoặc thu hồi dữ liệu đã tải xong. Chỉ kết luận cho hành vi đã được đặc tả và kiểm chứng.

## 10. Kiểm thử lạm dụng bằng thao tác đồng thời

Một quy tắc có thể đúng khi gọi tuần tự nhưng sai khi hai yêu cầu cùng đọc trạng thái cũ.

Với SEC-EXP-05, giả sử đã có một tác vụ RUNNING của user-a trong tenant-a. Hai yêu cầu xuất mới tới gần đồng thời.

Nếu cả hai cùng thấy “đang có một tác vụ” rồi cùng tạo thêm, tổng sẽ thành ba, vượt giới hạn hai.

### 10.1. Thiết kế ca AB-EXP-03

Tiền điều kiện:

- Có đúng một tác vụ đang hoạt động của cặp user-a–tenant-a.
- Không có tác vụ khác của cùng cặp được tạo bởi ca chạy song song.
- Hai request mới là hai yêu cầu khác nhau, không bị gộp bởi cơ chế idempotency.
- Các điều kiện nghiệp vụ khác đều hợp lệ.

Hành động:

1. Chuẩn bị hai client cùng danh tính chủ thể và tenant.
2. Dùng điểm đồng bộ của test để phát hai request cạnh tranh trong phạm vi có kiểm soát.
3. Thu phản hồi và chờ các giao dịch liên quan hoàn tất.
4. Đọc số tác vụ hoạt động từ nguồn trạng thái có thẩm quyền.

Oracle:

- Tổng QUEUED và RUNNING không vượt hai ở phạm vi cần bảo đảm.
- Theo hợp đồng giả định của fixture này, một request được chấp nhận, request còn lại bị từ chối vì giới hạn.
- Không có tác vụ thừa nằm trong hàng đợi hoặc đầu ra không gắn với tác vụ hợp lệ.
- Audit và kết quả phản hồi khớp với quyết định.
- Quy tắc không bị vượt khi cùng chủ thể sử dụng hai phiên hoặc hai token hợp lệ.

Ví dụ API có thể đặc tả 202 cho request được nhận và 429 cho request vượt giới hạn. Phải xác định hợp đồng trước khi gắn các mã này vào assertion.

### 10.2. Giới hạn của phép thử đồng thời

Một lần chạy không xuất hiện lỗi chưa chứng minh mọi lịch xen kẽ đều an toàn. Có thể dùng nhiều lịch có kiểm soát, kiểm thử thành phần cho quyết định nguyên tử và rà soát cơ chế lưu trạng thái.

Kiểm thử giới hạn tác vụ đồng thời cũng khác kiểm thử số request trong một khoảng thời gian. Cần xác định đang kiểm tra quota trạng thái, tốc độ hay cả hai để tránh dùng sai oracle.

Không tăng số request vô hạn để thay cho thiết kế ca tốt. Một tình huống nhỏ với trạng thái ban đầu và điểm cạnh tranh rõ ràng thường giúp tái hiện lỗi dễ hiểu hơn.

## 11. Mở rộng abuse case sang các nhóm yêu cầu khác

| Nhóm | Mục tiêu lạm dụng minh họa | Yêu cầu và oracle cần làm rõ |
|---|---|---|
| Xác thực | Tiếp tục dùng phiên sau khi tài khoản bị khóa | Thời điểm khóa có hiệu lực, các đường xác thực, phiên cũ và kết quả truy cập sau giới hạn. |
| Phân quyền | Gọi trực tiếp API mà giao diện không hiển thị cho vai trò hiện tại | Quyết định quyền phía máy chủ, tác dụng phụ và ca đối chứng có quyền. |
| Dữ liệu | Lấy tệp xuất qua danh tính hoặc tenant khác | Quyền đọc tệp, phạm vi liên kết tải, nội dung đầu ra và cache liên quan. |
| Logging | Dùng trường do người dùng nhập để tạo bản ghi có vẻ như sự kiện quản trị | Nguồn danh tính tin cậy, cấu trúc sự kiện, xử lý dữ liệu nhập và khả năng phân biệt dữ liệu với metadata. |
| Phục hồi | Dùng danh tính ứng dụng để tác động cả dữ liệu chính lẫn bản sao lưu | Quyền bảo vệ bản sao, phạm vi tác động và khả năng khôi phục từ dữ liệu thử. |
| Tính sẵn sàng | Tạo nhiều tác vụ nặng trong giới hạn danh tính bị áp sai | Khóa tính quota, hành vi đồng thời, công việc được chấp nhận và tác động tới người dùng khác. |

Các kịch bản phải xuất phát từ khả năng thực tế và yêu cầu đã chọn. Không dùng một danh sách kỹ thuật chung để thay cho mô hình đe dọa của hệ thống.

Với ca phục hồi, chỉ sử dụng tập dữ liệu và bản sao được cấp cho kiểm thử, xác định rõ phạm vi trước khi mô phỏng mất hoặc sửa dữ liệu. Cần xác minh khôi phục được trạng thái cần thiết, không chỉ quan sát rằng thao tác bị từ chối.


## 12. Chọn biến thể và lập ma trận bao phủ

Không cần thử mọi tổ hợp ngẫu nhiên. Nên chọn biến thể theo ranh giới tin cậy, hành vi bắt buộc và những đường có thể bỏ qua điểm thực thi.

### 12.1. Các chiều biến thể hữu ích

- **Danh tính:** chưa đăng nhập, người dùng hợp lệ, thiếu quyền hành động, tài khoản bị khóa.
- **Phạm vi dữ liệu:** đúng tenant, khác tenant, cùng tenant nhưng tài nguyên bị giới hạn riêng.
- **Đường truy cập:** giao diện, API trực tiếp, worker, đường tải và công cụ quản trị nếu thuộc phạm vi.
- **Thời điểm:** trước khi được cấp quyền, sau khi tạo tác vụ, sau thu hồi và sau giới hạn đồng bộ.
- **Trạng thái:** chưa có tác vụ, gần giới hạn, đạt giới hạn, tác vụ kết thúc.
- **Tình huống lỗi:** không có quyết định quyền hợp lệ, cache quá cũ, phụ thuộc cần thiết không khả dụng.
- **Cạnh tranh:** hai yêu cầu mới, yêu cầu và thu hồi quyền cùng diễn ra, retry của một tác vụ.

Mỗi biến thể cần giữ các tiền điều kiện đủ rõ để biết đang kiểm chứng thuộc tính nào. Nếu vừa dùng token hết hạn vừa chọn tenant khác, kết quả 401 thường chỉ nói về xác thực.

Vai trò quản trị có quyền liên tenant được phê duyệt có thể có kết quả khác người dùng thường. Không dùng quy tắc “khác tenant luôn bị từ chối” nếu chính sách thực tế có những quyền đặc biệt được xác định.

### 12.2. Ma trận kế hoạch minh họa

| Ca | Mục tiêu lạm dụng | Yêu cầu chính | Điểm thực thi và bằng chứng |
|---|---|---|---|
| AB-EXP-01 | Xuất dữ liệu tenant khác qua API | SEC-EXP-01, 02, 03 | Phản hồi, tác vụ, dữ liệu, tệp và audit. |
| AB-EXP-02 | Dùng quyền đã thu hồi qua tác vụ chờ | SEC-EXP-04, 02 | Quyết định quyền tại worker, thời điểm thu hồi, trạng thái công bố. |
| AB-EXP-03 | Vượt hai tác vụ bằng yêu cầu đồng thời | SEC-EXP-05 | Phản hồi và trạng thái bền vững sau các giao dịch cạnh tranh. |
| AB-EXP-04 | Tải bằng liên kết cũ sau khi mất quyền | SEC-EXP-01, 04 | Đường tải mới và cũ, thời hạn thu hồi, dữ liệu được trả. |

Đây là ma trận kế hoạch, không phải bảng kết quả thực thi. Cần bổ sung phiên bản ca, phiên bản yêu cầu, phạm vi và trạng thái chạy khi đưa vào quản lý kiểm thử.

Bao phủ yêu cầu không đồng nghĩa bao phủ mọi cách tấn công. Một yêu cầu có liên kết tới một ca vẫn có thể thiếu worker, đường tải hoặc tình huống lỗi.

## 13. Chọn tầng kiểm thử phù hợp

### 13.1. Kiểm thử thành phần

Phù hợp để kiểm tra:

- Quy tắc cho phép hoặc từ chối theo bộ dữ kiện.
- Biên thời gian bằng đồng hồ điều khiển.
- Ánh xạ vai trò sang hành động.
- Điều kiện trạng thái và xử lý dữ kiện thiếu.

Tầng này giúp khoanh vùng lỗi nhanh nhưng chưa chứng minh dữ kiện đưa vào bộ quyết định là đáng tin cậy hoặc mọi endpoint đều gọi bộ quyết định.

### 13.2. Kiểm thử tích hợp

Phù hợp để kiểm tra:

- API lấy đúng danh tính đã xác minh.
- Tenant và tài nguyên được đối chiếu đúng ở tầng dữ liệu.
- Worker kiểm tra lại quyền với nguồn hoặc cơ chế cache thực tế.
- Quyết định quota có hiệu lực cùng giao dịch và hàng đợi.
- Audit liên kết được qua các thành phần.

Không thay chính cơ chế quyền đang kiểm chứng bằng một mock luôn trả từ chối. Những phụ thuộc được thay thế phải được ghi rõ trong kết quả.

### 13.3. Kiểm thử toàn luồng

Phù hợp để kiểm tra hành trình từ tạo tác vụ tới xử lý, công bố và tải. Nó có thể phát hiện đường đi vòng giữa các thành phần mà từng test riêng không thấy.

Tầng này cần fixture, đồng bộ và khả năng quan sát tốt để kết quả có thể giải thích. Không cần đưa mọi biến thể nhỏ vào toàn luồng nếu tầng thấp đã kiểm chứng và quan hệ tích hợp đã được xác nhận.

### 13.4. Rà soát thiết kế bổ trợ

Một bộ test hữu hạn không chứng minh không tồn tại endpoint bị bỏ sót hoặc một lịch cạnh tranh khác. Kết hợp kiểm thử với kiểm kê điểm truy cập, rà soát ranh giới tin cậy và điểm thực thi kiểm soát.

Kết luận nên phản ánh tổng bằng chứng, không chỉ số ca đã xanh.

## 14. Báo cáo kết quả và quản lý bằng chứng

### 14.1. Ý nghĩa của kết quả

| Kết quả | Cách hiểu |
|---|---|
| PASS | Tiền điều kiện hợp lệ; các tiêu chí được kiểm tra đều đạt trong phạm vi đã ghi. |
| FAIL | Có bằng chứng vi phạm tiêu chí đã xác định, chẳng hạn trả dữ liệu trái phép hoặc tạo tác vụ vượt giới hạn. |
| BLOCKED | Không thể thực hiện do thiếu điều kiện hoặc phụ thuộc, ví dụ không có môi trường hay fixture cần thiết. |
| INCONCLUSIVE | Có quan sát nhưng chưa đủ tin cậy để kết luận, ví dụ mất dữ liệu quan sát giữa chừng. |
| NOT RUN | Ca chưa được thực hiện. |

Mục tiêu lạm dụng đạt được thường khiến ca bảo vệ FAIL. Không dùng chữ “thành công” mà không chỉ rõ đang nói về thao tác lạm dụng hay kết quả kiểm thử.

Nếu phân quyền chặn đúng nhưng audit không đáp ứng, cần báo riêng kết quả từng yêu cầu và kết quả tổng hợp theo quy tắc của ca. Không gộp toàn bộ thành PASS chỉ vì dữ liệu chưa bị trả về.

Một ca chỉ kiểm tra phát hiện có thể PASS khi tạo được cảnh báo dù hành động vẫn xảy ra theo thiết kế. Kết quả đó không chứng minh yêu cầu ngăn chặn; phải đối chiếu đúng loại kiểm soát được yêu cầu.

### 14.2. Bằng chứng tối thiểu cho một lần chạy

- Mã ca, phiên bản ca và phiên bản yêu cầu.
- Bản ứng dụng, môi trường, cấu hình liên quan và phạm vi phụ thuộc thật hoặc được mô phỏng.
- Fixture, vai trò và quyền được sử dụng, không cần lưu bí mật xác thực.
- Thời điểm, chuỗi hành động và mã tương quan.
- Kết quả phản hồi đã giảm thiểu dữ liệu nhạy cảm.
- Các quan sát về trạng thái, tác vụ, tệp và audit theo oracle.
- Kết quả từng tiêu chí, giới hạn của lần chạy và liên kết phát hiện nếu trượt.

Ví dụ báo cáo rút gọn:

```text
Lần chạy: RUN-AB-EXP-01-07
Ca: AB-EXP-01 rev-1
Yêu cầu: SEC-EXP-01/02/03, phiên bản được ghi trong tập yêu cầu
Ứng dụng: build-218
Phạm vi: API, kho trạng thái, worker và kho tệp của môi trường kiểm thử
Chủ thể: fixture user-a, quyền xuất trong tenant-a
Đối chứng hợp lệ: Đạt
Phản hồi chéo tenant: 404, không có dữ liệu hoặc liên kết tải
Tác vụ được chấp nhận cho request: 0
Kết quả xuất trái phép: 0
Trạng thái hồ sơ đích: Không đổi
Audit từ chối: Đúng trường yêu cầu, không chứa bí mật
Kết quả: PASS
Giới hạn: Chưa kiểm tra thu hồi quyền và hành vi đồng thời trong lần này
```

Đây là báo cáo giả định để minh họa cấu trúc, không phải khẳng định hệ thống thật đã được chạy kiểm thử.

### 14.3. Khi phát hiện lỗi

Một phát hiện có ích cần giữ:

1. Tiền điều kiện và chuỗi hành động tái hiện.
2. Hành vi kỳ vọng đối chiếu với yêu cầu.
3. Hành vi quan sát được và bằng chứng.
4. Tài sản, phạm vi và hậu quả có thể suy ra từ bằng chứng.
5. Giới hạn: phần nào chưa được xác nhận.
6. Chủ sở hữu xử lý và ca hồi quy cần giữ.

Không suy ra “mọi tenant đều bị ảnh hưởng” chỉ từ một fixture nếu chưa có căn cứ về phạm vi. Đồng thời, không hạ thấp lỗi chỉ vì dữ liệu dùng để chứng minh là dữ liệu tổng hợp.

Sau khi sửa, chạy lại ca liên quan và các phần hồi quy có tác động. Bản sửa một endpoint chưa chứng minh worker hoặc đường tải đã được bảo vệ.

## 15. Duy trì abuse case test trong vòng đời yêu cầu

Ca kiểm thử cần được xem lại khi:

- Yêu cầu đổi phạm vi, ngưỡng hoặc hành vi khi lỗi.
- Thêm endpoint, worker hoặc kiểu chủ thể mới.
- Đổi nguồn danh tính, cache quyền hoặc cơ chế tải tệp.
- Đổi quy tắc trạng thái hoặc định nghĩa tác vụ đang hoạt động.
- Sự cố phát hiện đường lạm dụng chưa có trong mô hình.
- Triển khai thay đổi điểm thực thi hoặc phụ thuộc dùng chung.

Khi yêu cầu đổi, giữ lịch sử của ca và bằng chứng cũ. Không chỉ gắn phiên bản yêu cầu mới lên báo cáo đã chạy trước đó.

Ví dụ, nếu SEC-EXP-04 đổi giới hạn thu hồi từ 60 giây xuống 15 giây, ca kiểm thử, cách đo và điều kiện tích hợp đều cần được đánh giá lại. Bằng chứng đáp ứng 60 giây chưa đủ chứng minh 15 giây.

Những abuse case quan trọng nên được giữ trong bộ hồi quy theo tầng phù hợp. Lịch chạy cần xét độ rủi ro, chi phí, độ ổn định và loại thay đổi; không mặc định mọi ca toàn luồng phải chạy ở mọi thao tác chỉnh sửa.

## 16. Lỗi thường gặp

| Lỗi | Vì sao kết luận thiếu căn cứ | Cách điều chỉnh |
|---|---|---|
| Chỉ kiểm tra mã 4xx | Có thể do token hỏng, schema sai hoặc route không tồn tại | Xác minh tiền điều kiện và dùng mã đúng hợp đồng. |
| Không có ca hợp lệ đối chứng | Dịch vụ hỏng cũng làm ca lạm dụng bị chặn | Chứng minh chức năng được phép vẫn hoạt động. |
| Dùng observer để gọi hành động | Quyền thực tế khác chủ thể được mô hình hóa | Tách client chủ thể và kênh quan sát. |
| Chỉ nhìn phản hồi API | Worker hoặc outbox vẫn có thể tạo kết quả trái phép | Theo dõi trạng thái bền vững và luồng bất đồng bộ. |
| Đợi cố định rồi kiểm tra không có tệp | Bỏ sót xử lý muộn hoặc nhầm do môi trường chậm | Dùng điểm hoàn tất, nguồn quan sát và thời hạn đã xác định. |
| Mock sẵn quyết định từ chối | Không kiểm chứng được cơ chế quyền hoặc tích hợp thực | Kiểm tra cơ chế thật ở tầng phù hợp. |
| Chỉ gọi tuần tự | Không kiểm tra được quyết định cạnh tranh | Thiết kế trạng thái và lịch đồng thời có kiểm soát. |
| Dùng token hết hạn để thử tenant isolation | Chỉ chạm tới xác thực | Giữ token hợp lệ và thay phạm vi tài nguyên. |
| Yêu cầu mọi trạng thái phải không đổi | Audit hoặc bộ đếm hợp lệ có thể cần thay đổi | Chỉ rõ tác dụng phụ bị cấm và tác dụng phụ được yêu cầu. |
| Chạy lại đến khi xanh | Che khuất race hoặc mất quan sát | Giữ lần lỗi và phân tích nguyên nhân trước khi kết luận. |
| Đồng nhất số test với mức an toàn | Nhiều ca có thể cùng kiểm tra một đường | Theo dõi rủi ro, điểm thực thi và biến thể còn thiếu. |

## 17. Bài tập thực hành

Một hệ thống có hai tenant A và B. user-a có quyền xuất trong A. API tạo tác vụ, worker xử lý và kho tệp phục vụ tải xuống.

Nhóm đã có một test:

```text
Gửi request với token hết hạn và documentId của tenant B.
Nhận 401.
Kết luận: tenant isolation đạt.
```

Hãy thực hiện:

1. Giải thích yêu cầu nào thực sự được chạm tới và vì sao chưa đủ kiểm chứng tenant isolation.
2. Viết lại tiền điều kiện và ca đối chứng dùng token hợp lệ của user-a.
3. Xác định mục tiêu lạm dụng, chuỗi hành động và hợp đồng phản hồi mong đợi.
4. Bổ sung oracle cho kho trạng thái, worker, tệp xuất và audit.
5. Viết một biến thể thu hồi quyền sau khi tạo tác vụ, dùng giới hạn thu hồi đã được xác định.
6. Viết một biến thể hai request cạnh tranh khi đã có một tác vụ hoạt động và giới hạn là hai.
7. Nêu điều kiện khiến ca BLOCKED hoặc INCONCLUSIVE thay vì PASS.
8. Liệt kê bằng chứng cần giữ khi test bị trượt và phần cần chạy lại sau sửa.

### Gợi ý tự đánh giá

- 401 với token hết hạn có thể là kết quả đúng cho xác thực, nhưng quá trình chưa tới quyết định quyền của chủ thể hợp lệ trên tài nguyên B.
- Ca đối chứng phải chứng minh user-a thực sự có thể xuất tài nguyên A qua đúng luồng.
- Ca chính cần tài nguyên B tồn tại và thuộc B, cùng danh tính A được xác thực hợp lệ.
- Từ chối ở API không đủ nếu vẫn có tác vụ hoặc tệp trái phép; phải quan sát đúng điểm hoàn tất.
- Thu hồi quyền cần được gắn với nguồn có thẩm quyền, độ trễ cho phép và các điểm kiểm tra thực tế.
- Ca đồng thời phải kiểm tra trạng thái cuối cùng và công việc đã được chấp nhận, không chỉ hai mã phản hồi.
- Nếu kênh quan sát bị lỗi hoặc chưa biết worker đã kết thúc hay chưa, không được chuyển thiếu bằng chứng thành PASS.
- Sau sửa, giữ ca tái hiện làm hồi quy và xem lại những đường cùng dùng cơ chế quyền.

## 18. Câu hỏi tự kiểm tra

1. Vì sao một người dùng đã đăng nhập vẫn có thể là chủ thể của abuse case?
2. Mục tiêu lạm dụng khác chuỗi request dùng để thử ở điểm nào?
3. Tại sao mã lỗi đúng chưa đủ để kết luận yêu cầu bảo mật đạt?
4. Ca đối chứng giúp loại bỏ những kết luận sai nào?
5. Khi nào cần quan sát tác vụ, tệp hoặc hàng đợi thay vì chỉ dữ liệu phản hồi?
6. Vì sao sleep cố định không thay thế được điểm hoàn tất của xử lý bất đồng bộ?
7. Test dùng đồng hồ giả chứng minh được gì và chưa chứng minh được gì?
8. Tại sao quota tác vụ đồng thời khác giới hạn số request theo thời gian?
9. Bằng chứng của test phát hiện có thể được dùng để kết luận ngăn chặn không?
10. Những thay đổi nào làm abuse case test và bằng chứng cũ cần được đánh giá lại?

