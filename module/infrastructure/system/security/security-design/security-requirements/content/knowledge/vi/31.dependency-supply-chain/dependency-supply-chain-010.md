# Plugin security — Đặc tả yêu cầu bảo mật cho cơ chế mở rộng

## 1. Plugin là gì và vì sao cần yêu cầu riêng?

**Plugin** là thành phần mở rộng được host nạp hoặc gọi thông qua một hợp đồng tích hợp để bổ sung chức năng. Plugin có thể chạy lúc build, lúc khởi động hoặc khi xử lý một tác vụ; nó có thể nằm cùng tiến trình với host hoặc chạy trong một môi trường thực thi riêng.

Ví dụ gồm plugin build, bộ chuyển đổi tài liệu, trình xử lý sự kiện, connector, extension quản trị hoặc module báo cáo. Cơ chế đóng gói khác nhau nhưng câu hỏi bảo mật giống nhau: ai được đưa mã vào, mã đó chạy với quyền nào, tiếp cận dữ liệu gì và làm sao dừng quyền khi không còn được tin cậy?

Trong chương **Dependency và supply chain**, thuộc module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, mục tiêu không dừng ở “chỉ cài plugin đáng tin”. Cần chuyển mục tiêu an toàn và mô hình đe dọa thành yêu cầu cụ thể, đo được, có owner và bằng chứng kiểm thử về nguồn mã, xác thực, phân quyền, dữ liệu, logging và phục hồi.

Sau bài học, người học cần có khả năng:

- Phân biệt kiểm chứng nguồn plugin với việc cho phép plugin hoạt động.
- Chọn ranh giới cách ly theo mức độ tin cậy của mã và tác động nghiệp vụ.
- Đặc tả quyền được yêu cầu, quyền được cấp và quyền được thực thi ở mỗi lần gọi.
- Kiểm soát cài đặt, nâng cấp, callback, dữ liệu đầu ra, quota và thu hồi.
- Liên kết rủi ro với thiết kế, test đối kháng, acceptance criteria và runbook.

Các ID plugin, schema, URI tham chiếu và ngưỡng trong bài là ví dụ học tập. Chúng phải được điều chỉnh theo khả năng của host và nền tảng thực thi, không phải cấu hình dùng chung cho mọi sản phẩm.

## 2. Phạm vi và ranh giới tin cậy

### 2.1. Plugin khác một dependency thông thường ở đâu?

Một thư viện cố định trong ứng dụng cũng là một phần của supply chain. Cơ chế plugin thường bổ sung khả năng khám phá, cài/nâng cấp, đăng ký hook hoặc cấp quyền độc lập sau khi host được phát hành. Điều đó làm xuất hiện thêm bề mặt quản lý và thời điểm thay đổi quyền.

Không phải cứ gọi là plugin thì mã ít quyền hơn thư viện. Nếu plugin chạy trực tiếp trong tiến trình host với cùng quyền hệ điều hành, nó có thể có quyền thực tế tương đương host dù API tài liệu chỉ công bố vài callback.

| Mô hình | Đặc điểm | Giới hạn bảo đảm cần nêu |
| --- | --- | --- |
| Cùng tiến trình, cùng quyền | Dễ gọi API/đối tượng host, chi phí tích hợp thấp | Không phù hợp để tuyên bố cách ly mã tùy ý độc hại chỉ bằng interface hoặc classloader |
| Tiến trình riêng | Có thể tách danh tính, tài nguyên và giao tiếp | Chỉ tách process chưa đủ nếu vẫn đọc secret host, dùng quyền rộng hoặc truy cập socket quản trị |
| Môi trường có sandbox thực thi | Có các giới hạn thực sự do runtime/hệ điều hành/nền tảng cưỡng chế | Phải kiểm chứng filesystem, mạng, syscall/tính năng nền tảng, tài nguyên và khả năng thoát ranh giới theo thiết kế |
| Dịch vụ từ xa | Plugin chạy ngoài host qua một API | Cần xác thực hai phía theo hợp đồng, giới hạn dữ liệu, tenant, deadline và quản lý đích kết nối |
| Plugin build | Có thể chạy trước khi sản phẩm được tạo | Credential ký/phát hành, source và artifact đầu ra có thể bị ảnh hưởng dù plugin không được ship |

Classloader và module của Java hỗ trợ tổ chức/nạp mã và kiểm soát một số quan hệ truy cập, nhưng không tự tạo sandbox cho mã Java tùy ý không được tin cậy. Không dựa vào việc “chỉ truyền một interface” để bảo đảm plugin cùng JVM không tiếp cận các khả năng khác của tiến trình.

### 2.2. Chuỗi ranh giới cần mô tả

```text
Nguồn plugin / registry / publisher
             |
             v
Cổng quản lý: kiểm chứng package + phê duyệt nguồn, digest và quyền
             |
             v
Staging chưa được phép thực thi nghiệp vụ
             |
             v
Runtime riêng theo thiết kế cách ly
  [danh tính riêng, filesystem/mạng/quota được cưỡng chế]
             |
             | API hẹp, caller được xác thực
             v
Broker của host
  [policy + grant + quyền người dùng/job + tenant/object + trạng thái thu hồi]
             |
             v
Dữ liệu và tác dụng nghiệp vụ được phép
```

Kết quả plugin trả về đi qua một ranh giới dữ liệu ngược lại. Host vẫn phải kiểm tra schema, kích thước, ngữ nghĩa và cách dữ liệu được sử dụng ở đích cuối. Plugin không được tự cấp quyền cho mình bằng cách trả một field `approved=true` hoặc yêu cầu host thực hiện một hành động ngoài grant.

## 3. Mô hình đe dọa và bất biến

### 3.1. Tài sản và giả định

Tài sản cần bảo vệ gồm quyền của host, dữ liệu người dùng/tenant, credential, source và artifact build, tính đúng đắn của thao tác nghiệp vụ, tài nguyên thực thi và bằng chứng audit.

Giả định có thể tồn tại plugin lỗi hoặc độc hại, publisher bị chiếm quyền, package bị thay, người dùng có quyền yêu cầu plugin nhưng không được quản trị host, hoặc một callback/dữ liệu trả về được chuẩn bị để vượt quyền. Không giả định chữ ký đúng làm mã trở thành vô hại.

Nếu plugin được cấp quyền trực tiếp thực hiện một thao tác, phải xem xét khả năng nó dùng quyền đó không đúng ý định. Least privilege giảm phạm vi hậu quả; nó không tự chứng minh plugin xử lý dữ liệu đúng. Với tác dụng nhạy cảm, host cần kiểm tra nghiệp vụ và chính sách tại điểm thực thi.

| Risk ID | Kịch bản | Hậu quả cần ngăn | Hướng kiểm soát |
| --- | --- | --- | --- |
| PLR-01 | Package/nguồn cập nhật bị đánh tráo hoặc publisher bị chiếm | Thực thi mã không được phép | Ràng buộc danh tính nguồn, digest, phiên bản và phê duyệt |
| PLR-02 | Manifest xin ít quyền nhưng mã gọi khả năng khác | Vượt grant bằng quyền môi trường | Cách ly thực sự và broker kiểm tra mỗi yêu cầu |
| PLR-03 | Plugin kế thừa biến môi trường, file cấu hình hoặc credential host | Đọc bí mật rồi lạm dụng/xuất dữ liệu | Danh tính, environment, filesystem và handle tối thiểu |
| PLR-04 | Plugin đổi tenant/object trong request tới broker | Truy cập dữ liệu ngang tenant hoặc thao tác thay người khác | Context từ host, kiểm tra object-level và grant có phạm vi |
| PLR-05 | Plugin làm host gọi URL/đường dẫn tùy ý | SSRF, đọc file ngoài phạm vi, rò rỉ credential | API hẹp và kiểm soát đích/path tại broker cùng egress |
| PLR-06 | Plugin treo, cấp phát vô hạn hoặc sinh nhiều tiến trình | Làm cạn tài nguyên và lan sự cố sang host | Quota, deadline, giới hạn cây tiến trình và hàng chờ |
| PLR-07 | Archive cài đặt có traversal, link hoặc tên file xung đột | Ghi đè file host hoặc nạp mã ngoài package được duyệt | Kiểm tra giải nén trong staging, ràng buộc nội dung và quyền ghi |
| PLR-08 | Dependency/native library hoặc mã tải động nằm ngoài phần đã kiểm chứng | Chạy mã không thuộc artifact được phê duyệt | Bao phủ dependency và kiểm soát nạp mã sau kích hoạt |
| PLR-09 | Update mở rộng permission mà kế thừa phê duyệt cũ | Tăng quyền không được chấp thuận | Diff quyền, phê duyệt theo phiên bản/digest và cấp lại grant |
| PLR-10 | Thu hồi nhưng instance, callback hoặc capability cũ còn hoạt động | Tiếp tục đọc/ghi sau khi mất quyền | Điểm kiểm tra thu hồi và dừng thực thi có thời hạn |
| PLR-11 | Host tin dữ liệu đầu ra hoặc deserialize đối tượng tùy ý | Vượt ranh giới dữ liệu, thực thi/hiển thị ngoài ý muốn | Schema dữ liệu hẹp, kiểm tra sink và không nạp kiểu theo dữ liệu không tin cậy |
| PLR-12 | Retry/callback lặp tạo tác dụng nhiều lần | Cập nhật/gửi/thu phí lặp | Danh tính operation, idempotency và trạng thái kết quả chưa rõ |
| PLR-13 | Rollback phục hồi plugin/digest đã bị chặn | Làm sống lại mã hoặc quyền đã thu hồi | Đối chiếu policy hiện hành trước khởi động lại |
| PLR-14 | Plugin ghi secret vào log hoặc kết quả dùng chung | Lộ dữ liệu giữa tenant hoặc tới kênh quan sát | Tối thiểu dữ liệu, kiểm soát kênh ra và phạm vi lưu trữ |

### 3.2. Bất biến bảo mật

1. Chỉ nội dung và quyền đã được phê duyệt cho đúng plugin/digest mới được kích hoạt.
2. Plugin không tự chọn danh tính tin cậy, tenant hoặc quyền người dùng để host xử lý thay.
3. Quyền được khai báo không tự thành quyền được cấp; quyền được cấp không vượt chính sách tại lúc sử dụng.
4. Plugin không có đường vòng tới dữ liệu, credential hoặc quyền quản trị mà broker đang bảo vệ.
5. Thu hồi phải làm mất khả năng tạo thao tác mới trong thời hạn đã công bố, kể cả với instance và grant cũ.
6. Lỗi, timeout, update và rollback không được kích hoạt mã hoặc quyền trái chính sách.

## 4. Hồ sơ plugin và mô hình quyền

### 4.1. Hồ sơ tối thiểu

| Trường | Điều cần đặc tả |
| --- | --- |
| Plugin ID, publisher, owner | Danh tính ổn định, nguồn được phép, đội chịu trách nhiệm |
| Artifact và bằng chứng nguồn | Digest, định dạng package, chữ ký/chứng thực và danh tính được ủy quyền |
| Phiên bản và tương thích | API/protocol/hook được dùng, version host hỗ trợ và hành vi khi không tương thích |
| Dependency | Mã đi kèm, native library, thành phần tải thêm, bằng chứng inventory phù hợp |
| Điểm vào và hook | Khi nào được gọi, ai kích hoạt, dữ liệu vào/ra và tác dụng có thể phát sinh |
| Quyền yêu cầu/được cấp | Operation, tenant, object/resource, đích kết nối, thời hạn và giới hạn |
| Mô hình cách ly | Cùng process hay process riêng, danh tính, filesystem, mạng và quyền nền tảng |
| Ngân sách | CPU/memory/wall time, tiến trình, đồng thời, queue và kích thước dữ liệu |
| Vòng đời | Staging, activate, update, disable, revoke, stop và rollback |
| Quan sát/phục hồi | Audit, metric, owner xử lý, thời hạn thu hồi, dữ liệu/plugin state cần giữ |

Manifest có thể công bố một số trường này, nhưng manifest là đầu vào cần kiểm chứng. Một field `publisher: trusted-team` chưa chứng minh ai đã phát hành; một field `sandboxed: true` chưa chứng minh runtime thực thi sandbox.

### 4.2. Quyền hiệu lực là giao của các điều kiện

Một mô hình khái niệm:

```text
quyền hiệu lực =
    quyền mà policy hệ thống cho phép
  ∩ quyền phê duyệt cho đúng plugin/digest
  ∩ quyền trong grant còn hiệu lực của instance/job
  ∩ quyền của người dùng hoặc service job theo context host
  ∩ phạm vi tenant/object/tác vụ được phép tại điểm thực thi
```

Mô hình không có nghĩa cứ cộng đủ các cờ là mọi thao tác được phép. Broker còn phải kiểm tra trạng thái plugin/publisher, thu hồi, quota và điều kiện nghiệp vụ. Một tác vụ nền không có người dùng trực tiếp vẫn cần service principal và phạm vi job được định nghĩa; không mặc định nó được chạy với quyền admin host.

Ưu tiên operation có ý nghĩa hẹp, chẳng hạn `orders.readSummary`, thay cho `executeSql`, `readAnyFile` hoặc `fetchAnyUrl` nếu nhu cầu chỉ là tạo thống kê. API hẹp giúp broker kiểm tra object/tenant, lọc field và audit quyết định rõ ràng.

## 5. Bộ yêu cầu có thể kiểm chứng

Bảng sau dùng các ngưỡng nghiệm thu minh họa. Owner phải chốt phạm vi áp dụng và chứng minh nền tảng thực thi đạt chúng; không đánh dấu đạt chỉ vì manifest có đúng giá trị.

| ID | Yêu cầu | Owner | Bằng chứng đạt |
| --- | --- | --- | --- |
| PLG-01 | Mỗi plugin phải có hồ sơ nguồn, artifact/digest, owner, hook, dữ liệu, quyền và mô hình cách ly được phê duyệt trước kích hoạt. | Chủ host/bảo mật | Thiếu trường hoặc chưa phê duyệt không tạo instance được nhận job nghiệp vụ |
| PLG-02 | Chỉ nhận package từ danh tính/nguồn được phép; chứng thực phải ràng buộc đúng artifact và metadata cần cho quyết định. | Supply chain/release | Sửa package, đổi signer không được phép hoặc dùng bằng chứng của bản khác đều không được kích hoạt |
| PLG-03 | Phần mã được phép chạy phải bao phủ dependency/native library và cơ chế nạp thêm theo policy; plugin không tự tải mã mới để vượt kiểm chứng. | Build/runtime | Fixture tải dependency/mã ngoài tập được duyệt bị chặn hoặc đi qua luồng phê duyệt riêng trước dùng |
| PLG-04 | Cài đặt phải kiểm soát archive/path/link, quota và staging chưa thực thi. Ví dụ package nén không quá 20 MiB, sau giải nén 50 MiB, tối đa 1.000 file. | Nền tảng | Traversal, đường dẫn tuyệt đối, link ra ngoài, xung đột tên và archive vượt ngân sách không ghi ngoài staging hoặc chạy mã |
| PLG-05 | Mô hình cách ly phải cưỡng chế quyền theo mức tin cậy. Không tuyên bố mã tùy ý cùng quyền tiến trình đã bị sandbox chỉ bằng API/classloader. | Kiến trúc/runtime | Kiểm thử đọc file/secret host, gọi khả năng ngoài API và truy cập quyền nền tảng; chứng minh ranh giới thực tế |
| PLG-06 | Grant phải gắn plugin/digest/instance, tenant/job, operation/resource, thời hạn và policy/epoch thu hồi. Plugin không được tự nâng hoặc chuyển grant sang context khác. | Chủ host/IAM | Grant giả, hết hạn, sai instance/tenant/digest hoặc đã bị thu hồi đều bị broker chặn |
| PLG-07 | Broker phải xác thực caller và kiểm tra quyền người dùng/job, grant, object-level và điều kiện nghiệp vụ trước tác dụng. Tenant không lấy từ field plugin tự khai. | Ứng dụng/IAM | Đổi tenant/object, gọi operation ngoài grant và dùng quyền host thay người dùng không tạo tác dụng trái phép |
| PLG-08 | Plugin không có ambient credential, filesystem/handle/mount/socket quản trị hoặc mạng cho phép đi vòng broker. Đích hợp lệ phải theo phạm vi được duyệt. | Nền tảng/runtime | Plugin thử đọc environment/file host, gọi metadata/dịch vụ nội bộ hoặc broker quản trị; không có đường quyền ngoài hợp đồng |
| PLG-09 | Ví dụ mỗi job có wall time 5 giây, CPU budget 2 giây, memory 128 MiB, tối đa 16 tiến trình trong nhóm thực thi và output 1 MiB. Quota phải gồm tiến trình con theo thiết kế. | Runtime | Loop, cấp phát, fork/spawn, output quá cỡ và child còn sống sau job đều được xử lý trong giới hạn đã đặc tả |
| PLG-10 | Giới hạn đồng thời/hàng chờ phải có phạm vi. Ví dụ tối đa 2 job đang chạy cho một tenant và 20 job chờ, có cơ chế phối hợp nếu quota là toàn dịch vụ. | Nền tảng | Thử qua nhiều replica, overload và tenant khác; không nhân quota ngoài hợp đồng hoặc gây starvation không kiểm soát |
| PLG-11 | Đầu vào, callback và output phải có schema, version, kích thước, xác thực/context phù hợp; không deserialize kiểu tùy ý hoặc coi output là lệnh quản trị. | Ứng dụng/runtime | Output sai schema, callback giả, field tự nhận quyền và dữ liệu nguy hiểm cho sink không được thực thi như quyền host |
| PLG-12 | Tác dụng và retry/callback lặp phải dùng định danh operation cùng idempotency/đối soát phù hợp. Timeout không tự chứng minh thao tác chưa xảy ra. | Ứng dụng | Mất response sau commit, callback trùng và crash không tạo thêm tác dụng bị cấm |
| PLG-13 | Update phải kiểm tra digest, tương thích, dependency và chênh lệch quyền; quyền mới không kế thừa im lặng từ phê duyệt cũ. | Release/chủ host | Bản nâng cấp xin thêm operation/mạng hoặc sửa hook bị giữ staging cho tới khi được phê duyệt đúng |
| PLG-14 | Ví dụ sau quyết định revoke được commit, broker chặn thao tác mới chậm nhất 30 giây và runtime dừng nhóm thực thi chậm nhất 60 giây. Grant/cache cũ không vượt thời hạn này. | IAM/runtime/vận hành | Kiểm tra mọi replica, instance/grant cũ, child và callback; ghi thời điểm quyết định, chặn và dừng thực tế |
| PLG-15 | Disable/revoke và rollback phải có nghĩa rõ; bản/digest đã bị chặn không được phục hồi bằng rollback hoặc restore cấu hình cũ. | Release/vận hành | Rollback tới bản đã thu hồi bị chặn theo policy hiện hành; request đang chạy được xử lý theo quy tắc đã công bố |
| PLG-16 | Audit ghi plugin/digest/instance, tenant/job reference được phép, operation, quyết định, reason và policy revision; không ghi secret hoặc dữ liệu nghiệp vụ dư thừa. | Vận hành/bảo mật | Truy vết được grant, update, deny và revoke; log/output không làm lộ dữ liệu hay trộn tenant |
| PLG-17 | Lỗi policy store, broker, kiểm chứng hoặc sandbox không được làm chuyển sang chạy cùng quyền host hoặc bỏ kiểm tra. | Chủ host/runtime | Tiêm lỗi phụ thuộc; chỉ degraded mode được duyệt mới hoạt động, không có fallback đặc quyền |
| PLG-18 | Có quy trình phát hiện plugin bị chiếm, giữ bằng chứng, khoanh vùng và khôi phục có kiểm chứng; quyền cũ phải được đánh giá lại trước mở lưu lượng. | Ứng phó/chủ host | Diễn tập revoke, tìm tenant/job bị ảnh hưởng và restore mà không phục hồi mã/quyền đã bị chặn |

## 6. Tiếp nhận package và kiểm soát vòng đời

### 6.1. Kiểm chứng trước khi thực thi

Không chạy installer, hook, code generator hoặc entrypoint của plugin chỉ để đọc manifest. Phân tích package chưa được tin cậy cũng phải có giới hạn tài nguyên và cơ chế parser/giải nén an toàn.

Luồng minh họa:

1. Tra plugin/publisher theo registry được kiểm soát; kiểm tra ai có quyền yêu cầu cài vào môi trường nào.
2. Nhận package vào vùng staging chưa thực thi, giới hạn kích thước và số lượng.
3. Xác minh nguồn/chứng thực và digest theo trust policy độc lập với package đang kiểm tra.
4. Đọc manifest bằng schema/version được hỗ trợ; đối chiếu dependency, hook và quyền yêu cầu.
5. Giải nén có kiểm soát nếu cần; kiểm tra nội dung, layout và đường dẫn được loader thực sự sử dụng.
6. Đối chiếu với policy, chạy kiểm thử phù hợp và phê duyệt quyền cho đúng digest.
7. Khởi tạo môi trường cách ly, xác minh các kiểm soát có hiệu lực rồi mới kích hoạt nhận job.
8. Lưu bằng chứng nguồn, nội dung, permission diff, policy revision và quyết định.

Digest của package, metadata và bằng chứng cần được ràng buộc đúng theo cơ chế ký/chứng thực đã chọn. Nếu manifest nằm trong package, nó phải thuộc phần nội dung được bảo vệ; nếu có metadata ngoài package ảnh hưởng quyền, metadata đó cũng phải được xác thực/ràng buộc theo hợp đồng. Không tự tạo một vòng hash tự tham chiếu mà không có quy tắc định dạng rõ ràng.

Một chữ ký đúng nhưng thuộc publisher chưa được tổ chức ủy quyền vẫn không đủ để cài. Publisher được phép phát hành plugin A cũng không mặc nhiên được phát hành mọi plugin hoặc xin mọi quyền.

### 6.2. Archive và đường dẫn

Đặc tả giải nén phải xử lý ít nhất đường dẫn tuyệt đối, `..`, đường dẫn theo drive/UNC nếu nền tảng có hỗ trợ, symlink/hardlink, tên trùng và các quy tắc chuẩn hóa/case sensitivity của filesystem đích. Đường dẫn sau khi phân giải phải nằm trong staging dự kiến; không chỉ kiểm tra chuỗi tên có một tiền tố trông hợp lệ.

Không cho một file giải nén trước tạo link rồi file sau dùng link đó để ghi ra ngoài. Cần kiểm soát đường đi và loại đối tượng trong quá trình tạo file, dùng vùng riêng với quyền phù hợp. Không tự giải nén archive lồng nhau hoặc tải tài nguyên từ xa khi hợp đồng không yêu cầu.

Sau kiểm chứng, mã cài đặt phải bất biến đối với plugin và đối tượng có quyền thấp hơn loader. Tránh kiểm tra hash một file rồi nạp một file khác cùng tên từ thư mục có thể bị ghi đè. Classpath, native library search path, script/helper và cấu hình nạp động cũng phải nằm trong phạm vi được kiểm soát.

### 6.3. Các trạng thái phải có ý nghĩa riêng

| Trạng thái | Ý nghĩa | Quyền thực thi nghiệp vụ |
| --- | --- | --- |
| DISCOVERED | Đã biết có một package/phiên bản | Chưa có |
| VERIFIED | Đã kiểm tra những bằng chứng nội dung/nguồn được yêu cầu | Chưa tự có quyền hoạt động |
| STAGED | Đang chờ phê duyệt, kiểm thử hoặc thiết lập runtime | Không nhận job nghiệp vụ bình thường |
| ACTIVE | Đúng digest, quyền được cấp và runtime đạt điều kiện hiện hành | Chỉ theo grant, context và policy ở từng operation |
| DRAINING | Không nhận job mới, xử lý job cũ theo thời hạn/chính sách | Không vượt các kiểm tra quyền/thu hồi đang có hiệu lực |
| DISABLED | Bị tắt theo cấu hình/vận hành có nghĩa được công bố | Không tạo job mới; job cũ phải có quy tắc dừng/drain rõ |
| REVOKED | Nội dung/nguồn/quyền không còn được phép | Chặn operation mới và dừng runtime theo ngân sách thu hồi |
| QUARANTINED | Có vấn đề cần điều tra hoặc sửa bằng chứng | Không được tự chuyển sang chạy đặc quyền để “thử lại” |

Tắt nút trên giao diện quản lý không chứng minh instance đã dừng hoặc capability đã vô hiệu. Một thay đổi trạng thái cần được truyền tới loader, broker, scheduler, callback và các replica theo thiết kế.

## 7. Ví dụ: plugin báo cáo chỉ đọc dữ liệu tối thiểu

Giả sử host quản lý đơn hàng và cho plugin `demo-report` tạo thống kê từ một tập đơn hàng đã được host cho phép. Plugin chạy trong môi trường riêng và không cần gọi Internet. Nó chỉ nhận summary của tối đa 100 đơn hàng được chọn trong context của một tenant/job.

Schema dưới đây là **hợp đồng minh họa của host**, không phải manifest chuẩn của một hệ sinh thái cụ thể.

```yaml
manifestVersion: 1
pluginId: demo-report
publisherId: demo-team
pluginVersion: 1.4.0
hostApi: report-broker-v1
entrypoint: report-summary

requestedPermissions:
  - orders.readSummary
requestedNetwork: none

input:
  schema: order-summary-input-v1
  maxOrders: 100
  allowedFields: [orderId, status, totalMinor]
output:
  schema: report-summary-output-v1
  maxBytes: 1048576

requestedExecution:
  wallTimeMs: 5000
  cpuTimeMs: 2000
  memoryMiB: 128
  maxProcesses: 16
```

Manifest chỉ là yêu cầu. Bản phê duyệt phía host gắn `pluginId`, publisher đã xác thực, artifact digest, quyền thực tế và policy revision. Ngưỡng runtime được cưỡng chế bởi nền tảng; plugin không được tự nâng memory hoặc bật mạng bằng cách sửa field trong package.

Host không đưa connection string database, cloud credential hoặc session quản trị vào plugin. Nếu plugin cần dữ liệu, nó gọi broker bằng một caller identity/instance đã được xác thực và một grant reference. Grant reference phải được ràng buộc với caller/context ở broker; biết reference không được tự biến thành quyền của tenant khác.

### 7.1. Luồng một job

```text
Người dùng/service principal yêu cầu báo cáo
  → host xác thực và xác định tenant/job cùng quyền object-level
  → host chọn đúng plugin digest đã được phê duyệt
  → scheduler đặt quota và tạo instance/job context được kiểm soát
  → cấp grant ngắn hạn, ví dụ tối đa 60 giây, chỉ orders.readSummary
  → plugin yêu cầu dữ liệu qua broker
  → broker xác thực caller + kiểm tra grant/policy/thu hồi/context/resource
  → broker lọc tối đa 100 order và các field được phép
  → plugin tính toán trong sandbox và trả dữ liệu theo schema
  → host validate output, kiểm tra điều kiện nghiệp vụ và lưu kết quả đúng tenant
  → kết thúc job, thu hồi grant, dừng nhóm thực thi và xử lý dữ liệu tạm
```

Tenant/job do host xác định từ context được tin cậy. Nếu plugin thêm `tenantId` khác trong request, broker không được dùng field đó để chọn tenant mới. Khi đọc object, broker còn phải lọc bằng quyền object-level của người dùng/job; có quyền xem một tenant không tự có quyền xem mọi object trong tenant đó.

Output của plugin là dữ liệu chưa được tin cậy. Host không dùng một field như `nextAction: admin.exportAll` làm lệnh đặc quyền. Nếu output được hiển thị thành HTML, mở trong spreadsheet hoặc dùng để tạo truy vấn/lệnh, từng sink cần xử lý phù hợp; JSON parse thành công chưa chứng minh dữ liệu an toàn cho mọi sink.

### 7.2. Phân quyền tối thiểu trong ví dụ

| Yêu cầu từ plugin | Kết quả mong đợi |
| --- | --- |
| Đọc summary của order được context cho phép | Broker trả đúng field và giới hạn số lượng |
| Đọc order thuộc tenant khác | Từ chối trước khi lộ dữ liệu, kể cả khi order ID tồn tại |
| Gọi `orders.write` hoặc yêu cầu credential database | Từ chối vì ngoài operation/grant được duyệt |
| Tự đổi grant reference sang instance khác | Từ chối khi caller/context không khớp |
| Truy cập network trực tiếp hoặc filesystem host | Bị ranh giới thực thi/mạng/filesystem chặn |
| Trả output quá 1 MiB hoặc sai schema | Không chấp nhận như kết quả hợp lệ; dừng/đánh dấu job theo policy |

## 8. Triển khai broker và kiểm tra quyền

### 8.1. Luồng quyết định

```text
broker_read_summary(request, authenticated_caller):
    require_request_schema_and_limits(request)
    caller = verify_runtime_instance_identity(authenticated_caller)
    grant = lookup_host_managed_grant(request.grant_reference)
    context = lookup_host_managed_job_context(grant.job_id)
    state = load_current_policy_and_revocation_state(caller.plugin_digest)

    require(state allows publisher, plugin_digest and instance)
    require(grant bound to caller, digest, instance, tenant and job)
    require(grant not expired and revocation state current enough by policy)
    require(operation allowed by policy, approval, grant and user/job authority)
    require_requested_resources_in_context_and_current_object_authorization()
    acquire_quota_with_atomic_scope_and_bounded_wait()
    read_using_host_selected_tenant_and_allowed_fields()
    audit_safe_decision_and_return_bounded_data()
```

Caller identity phải gắn với kênh và môi trường thực thi, không phải một `pluginId` tự khai trong body. Broker cần chống việc plugin A dùng grant của B ngay cả khi chúng dùng cùng API hoặc cùng tài khoản quản lý.

Kiểm tra grant và quota phải có tính nhất quán phù hợp với tác dụng. Nếu quota chỉ là chuỗi “đọc số đang chạy → tăng số” không được bảo vệ, nhiều replica có thể cùng vượt giới hạn. Nếu state thu hồi chưa đủ mới theo hợp đồng, không dùng cache vô hạn để cho phép operation.

### 8.2. Ví dụ Java kiểm tra một phần điều kiện grant

Ví dụ JDK 17 dưới đây minh họa phép giao quyền cho operation chỉ đọc. `Caller`, `Context`, `Grant` và `CurrentState` phải được broker tạo/tra từ nguồn tin cậy; không deserialize toàn bộ chúng từ JSON do plugin gửi. Parameter `now` do broker lấy từ nguồn thời gian đủ tin cậy, được tách ra để kiểm thử.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public final class PluginGrantPolicy {
    private static final String READ_SUMMARY = "orders.readSummary";

    public record Caller(String pluginId, String digest, String instanceId) {}
    public record Context(String tenantId, boolean userOrJobMayReadSummary) {}
    public record CurrentState(
            boolean publisherAllowed,
            boolean digestAllowed,
            boolean instanceActive,
            long revocationEpoch) {}

    public record Grant(
            Caller holder,
            String tenantId,
            Set<String> operations,
            Instant expiresAt,
            long revocationEpoch) {
        public Grant {
            Objects.requireNonNull(holder);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(expiresAt);
            operations = Set.copyOf(operations);
        }
    }

    public static boolean mayReadSummary(
            Caller actualCaller, Context context, Grant grant,
            CurrentState current, Instant now) {
        if (actualCaller == null || context == null || grant == null
                || current == null || now == null) {
            return false;
        }
        return current.publisherAllowed()
                && current.digestAllowed()
                && current.instanceActive()
                && grant.holder().equals(actualCaller)
                && grant.tenantId().equals(context.tenantId())
                && grant.operations().contains(READ_SUMMARY)
                && context.userOrJobMayReadSummary()
                && now.isBefore(grant.expiresAt())
                && grant.revocationEpoch() == current.revocationEpoch();
    }
}
```

Kết quả true chỉ cho biết phần điều kiện được biểu diễn trong hàm đã đạt. Ví dụ chưa kiểm tra job binding, object-level, quota, tính mới/nguồn của state thu hồi hoặc cách caller identity được xác thực. Các phần đó bắt buộc được thực hiện trong luồng broker trước khi đọc dữ liệu. Epoch phải do nguồn policy/thu hồi có thẩm quyền cấp, không phải số plugin tự chọn để khớp grant.

Tại thời điểm `now` bằng `expiresAt`, hàm trả false. Tăng epoch hoặc tắt instance/publisher/digest làm grant không còn thỏa điều kiện khi broker đã quan sát state mới. Muốn đạt ngân sách revoke 30 giây, thiết kế phân phối/cache state phải bảo đảm mọi điểm thực thi quan sát thay đổi trong hạn đó hoặc chặn khi không còn đủ tin cậy.

Một hàm kiểm tra quyền không cách ly plugin cùng tiến trình. Nó chỉ có tác dụng nếu plugin không có đường khác tới dữ liệu hoặc khả năng sửa nguồn context/policy mà hàm đang tin.

## 9. Cách ly thực thi và giới hạn tài nguyên

### 9.1. Không để quyền môi trường rộng hơn grant

Môi trường riêng cần có danh tính ít quyền, chỉ các file/volume cần thiết, thư mục mã không được plugin sửa, vùng ghi tạm có quota và network policy phù hợp. Không truyền toàn bộ environment của host hoặc kế thừa handle/socket quản trị chỉ vì tiện khởi tạo worker.

Container hoặc process riêng không tự bảo đảm những thuộc tính đó. Chạy với quyền đặc biệt, mount filesystem host, chia sẻ socket quản trị hoặc cấp danh tính cloud rộng có thể mở đường ngoài broker. Cần kiểm chứng các quyền thực tế, không chỉ nhãn “sandbox”.

Nếu plugin được phép dùng native code hoặc sinh tiến trình con, chính sách phải bao phủ các khả năng đó. Nếu không cần, từ chối chúng ở ranh giới thực thi phù hợp. Khi không chứng minh được cách ly mã không tin cậy, phải đổi mô hình chạy hoặc thay phạm vi plugin được chấp nhận.

### 9.2. CPU, memory, thời lượng và process tree

CPU time và wall time khác nhau: plugin có thể ngủ/chờ mãi nhưng dùng ít CPU, hoặc dùng nhiều core trong thời gian ngắn. Vì vậy ví dụ đặt cả CPU budget 2 giây lẫn wall time 5 giây. Cần nêu cách nền tảng tính CPU cho nhóm thực thi và hành vi khi vượt ngưỡng.

Memory quota cần bao phủ tài nguyên thuộc phạm vi đã hứa, không chỉ heap mà plugin tự khai trong runtime. Giới hạn output phải được thực thi khi nhận/stream, không đợi đọc hết dữ liệu vô hạn rồi mới kiểm tra. Giới hạn process phải tính cả child; dừng parent không chứng minh toàn bộ cây đã dừng.

Timeout broker hoặc hủy future ở host không tự dừng mã plugin hay hoàn tác tác dụng đã được chấp nhận. Cần cơ chế cưỡng chế kết thúc nhóm thực thi và thu hồi quyền ở điểm thực thi. Đo thời lượng bằng nguồn phù hợp của nền tảng, thường là đồng hồ đơn điệu cho khoảng thời gian nội bộ, thay vì dựa vào giờ lịch có thể bị chỉnh.

### 9.3. Dữ liệu còn lại và tái sử dụng worker

Sau job, cần xử lý grant, file tạm, bộ đệm, output dở dang và state dùng chung theo độ nhạy dữ liệu. Nếu tái sử dụng worker cho tenant khác, phải chứng minh job mới không đọc được dữ liệu/credential của job trước. Tạo một instance mới với vùng dữ liệu riêng có thể phù hợp hơn khi không kiểm chứng được reset.

Không dùng cache plugin toàn cục mà khóa chỉ có object ID nếu object ID có thể trùng giữa tenant. Phân vùng dữ liệu, định danh instance/job và quyền đọc kết quả vẫn cần được host cưỡng chế.

## 10. Callback, output và tác dụng nghiệp vụ

### 10.1. Giao tiếp hẹp và dữ liệu chưa được tin cậy

Protocol giữa host/broker và plugin cần định nghĩa version, loại message, field bắt buộc, kích thước, trạng thái job và hành vi khi nhận message không đúng thứ tự. Không cho dữ liệu đầu vào tùy ý chọn class, module hoặc executable mà host sẽ nạp.

Dùng mô hình dữ liệu hẹp và parser với tính năng phù hợp cho dữ liệu không tin cậy. Schema hợp lệ vẫn cần kiểm tra ngữ nghĩa, chẳng hạn order ID có thuộc job hay tổng/loại dữ liệu có phù hợp nghiệp vụ không. Plugin không được tự đổi job thành công hoặc đã được duyệt bằng một trường trong output.

Callback phải gắn với instance/job và danh tính gọi đã được xác thực theo kênh được chọn. Một job ID đoán được hoặc nằm trong log không đủ làm chứng cứ callback được phép. Nếu callback có thể đến lại, host cần quy tắc trạng thái và idempotency để không chấp nhận kết quả/tác dụng trùng.

### 10.2. Không suy kết quả từ timeout

Một plugin có thể yêu cầu broker tạo tác dụng rồi treo trước khi trả kết quả. Khi host timeout, tác dụng có thể đã commit. Retry với một operation ID mới có thể tạo thêm tác dụng ngoài ý muốn.

Yêu cầu cần nêu ai tạo operation ID, phạm vi tenant/plugin/job, thời hạn giữ trạng thái và cách xử lý kết quả chưa rõ. Với tác dụng ngoài host, cần khả năng idempotency phía đích hoặc quy trình tra cứu/đối soát tương ứng; ghi một marker ở host không tự tạo bảo đảm đúng một lần ở hệ thống khác.

Ví dụ plugin báo cáo chỉ đọc không cần quyền ghi đơn hàng. Nếu sau này thêm tính năng gửi báo cáo hoặc tạo khoản phí, đó là thay đổi quyền và tác dụng cần đặc tả/kiểm thử lại; không coi nó đã được cho phép bởi grant đọc summary.

## 11. Update, disable, revoke và phục hồi

### 11.1. Nâng cấp theo nội dung và chênh lệch quyền

Một bản plugin mới cần được đánh giá theo artifact digest, dependency, hook, schema, tương thích và quyền mới. Cùng plugin ID/publisher không có nghĩa mọi version được tự động nhận mọi grant cũ.

Lưu bản diff quyền và quyết định phê duyệt. Nếu version mới xin thêm `orders.write`, Internet hoặc một thư mục host, nó phải ở staging tới khi được duyệt đúng phạm vi. Nếu policy không cho phép quyền đó, từ chối kích hoạt chứ không chạy rồi chờ phát hiện lạm dụng.

Trong chuyển tiếp có thể drain instance cũ và tạo instance mới, nhưng grant phải gắn với đúng digest/instance. Không thay file plugin đang chạy trong thư mục mutable rồi giả định loader, broker và audit cùng hiểu một phiên bản.

### 11.2. Thu hồi có thời hạn và điểm chặn

Với ngân sách ví dụ của PLG-14:

```text
T0 = thời điểm quyết định revoke được commit ở nguồn có thẩm quyền
T0 + 30 giây: mọi broker phải từ chối operation mới của phạm vi bị revoke
T0 + 60 giây: nhóm thực thi liên quan phải được dừng theo hợp đồng runtime
```

Cần chỉ rõ nguồn thời gian, cách đo khoảng thời gian và phạm vi instance/replica. Request đến trước nhưng chỉ được broker chấp nhận sau mốc chặn cũng phải chịu policy tại điểm chấp nhận, không được dùng thời điểm client tự khai để đi qua.

Grant TTL 60 giây không tự đáp ứng yêu cầu chặn trong 30 giây. Broker phải có kiểm tra trạng thái/epoch hoặc cơ chế khác đáp ứng thời hạn, kể cả khi cache cũ còn dữ liệu. Nếu không liên lạc được nguồn thu hồi và không còn đủ bằng chứng theo độ mới cho phép, chặn operation nhạy cảm thay vì gia hạn cache vô hạn.

Quyết định mới có thể cần chặn theo publisher, plugin ID, một digest, một instance hoặc tenant/job. Không dùng một phạm vi quá hẹp để sót mã bị ảnh hưởng, cũng không mặc định xóa trạng thái/dữ liệu mọi tenant để giải quyết một instance lỗi. Phạm vi thu hồi phải có lý do, owner và bằng chứng.

Operation đã được chấp nhận trước điểm chặn có thể đã tạo tác dụng và không tự bị hoàn tác khi process bị dừng. Chính sách phải nêu phần nào được hủy, phần nào được hoàn tất có kiểm soát và phần nào cần đối soát. Không tuyên bố “revoke đã xóa mọi tác dụng trước đây”.

### 11.3. Rollback và restore

Rollback cũng là một quyết định kích hoạt. Kiểm tra lại digest, nguồn, dependency, quyền và danh sách chặn theo policy hiện hành. Một bản từng tốt có thể nay đã bị thu hồi hoặc có rủi ro chưa được chấp nhận.

Restore cần bảo toàn liên kết artifact, policy, approval, grant epoch, job và audit. Không phục hồi snapshot trạng thái cũ rồi coi các grant trước thu hồi lại hợp lệ. Nếu thời điểm/trạng thái không thể xác minh, giữ plugin chưa hoạt động cho tới khi tái cấp quyền đúng quy trình.

Nếu plugin cùng tiến trình đã có khả năng chiếm host, việc gọi hàm unload không chứng minh host sạch. Quy trình sự cố phải xét khả năng phục hồi host/runtime từ nguồn tin cậy và thay quyền/credential bị ảnh hưởng, không chỉ tắt một cờ plugin.

### 11.4. Plugin build

Plugin build cần được xem là mã được thực thi trên worker có thể đọc source và ảnh hưởng artifact. Không cấp credential ký/phát hành hoặc quản trị repository dài hạn chỉ vì worker cần chạy build.

Có thể tách worker build ít quyền với bước phê duyệt/ký/phát hành theo thiết kế tin cậy riêng. Quyền ghi artifact phải gắn với job/phạm vi cần thiết; đầu ra và bằng chứng build phải được liên kết, kiểm tra trước khi phát hành. Tách bước không tự chứng minh output không có mã độc; cần các kiểm soát supply chain và kiểm chứng sản phẩm theo rủi ro.

## 12. Logging, quan sát và runbook

Audit hữu ích gồm danh tính actor cài/update/revoke, plugin ID, artifact digest, publisher đã xác thực, instance/job reference, tenant reference được phép, operation, grant reference đã được xử lý an toàn, policy revision/epoch, reason code và thời điểm quyết định.

Không ghi capability/token có thể sử dụng lại, credential, toàn bộ input/output hoặc dữ liệu khác tenant vào log. Không coi mọi log do plugin tự phát là bằng chứng đáng tin của broker. Cần phân biệt “plugin nói đã bị từ chối” với quyết định thực tế tại điểm thực thi.

Metric có thể gồm kích hoạt bị chặn, permission deny, schema/output lỗi, quota/timeouts, hàng chờ, instance không dừng đúng hạn và độ trễ thu hồi. Hạn chế nhãn có cardinality cao; không đưa mọi job ID hoặc token thành nhãn toàn cục.

Runbook cần xác định owner, phạm vi thu hồi, điểm chặn, cách giữ bằng chứng, cách tìm tenant/job/tác dụng đã bị ảnh hưởng, điều kiện phục hồi và kiểm thử trước mở lại. Việc xử lý incident không được tắt sandbox hoặc dùng quyền host rộng hơn để “cho chạy tạm” plugin chưa đủ tin cậy.

## 13. Ma trận kiểm thử nghiệm thu

Dùng plugin thử cố ý vi phạm, dữ liệu tổng hợp và danh tính/khóa thử. Kiểm thử phải đi qua đúng loader, runtime, mạng, broker và topology triển khai cần bảo đảm; chỉ unit test một hàm quyền không chứng minh plugin đã được cách ly.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-PLG-01 | Package bị sửa; signer hợp lệ mật mã nhưng chưa được phép; manifest thiếu trường hoặc không tương thích | Không tạo instance nhận job bình thường; audit phân loại đúng lý do | PLG-01, 02 |
| T-PLG-02 | Archive có traversal, absolute path, link ra ngoài, tên xung đột và vượt từng quota cài đặt | Không ghi ngoài staging, không thực thi installer/hook để phân tích, không dùng output giải nén dở | PLG-04 |
| T-PLG-03 | Plugin thử nạp dependency/native/helper ngoài phần đã duyệt hoặc đổi nội dung sau kiểm tra | Bị ràng buộc loader/runtime chặn hoặc buộc qua quy trình kiểm chứng mới | PLG-02, 03 |
| T-PLG-04 | Grant sai digest/instance, hết hạn tại đúng biên, operation ngoài quyền; plugin gửi field quyền tự khai | Broker không dùng dữ liệu tự khai để cấp quyền; tất cả request trái grant bị từ chối | PLG-06, 07 |
| T-PLG-05 | Plugin đọc environment/file host, dùng handle/socket quản trị hoặc gọi network ngoài broker | Ranh giới thực thi chặn đường vòng; không chỉ nhìn lỗi do API plugin tự trả | PLG-05, 08 |
| T-PLG-06 | Đổi tenant/object; hai tenant có object ID trùng; worker được tái dùng sau job chứa dữ liệu thử | Không lộ object/field/kết quả tenant khác, không đọc được dữ liệu job trước | PLG-07, 08, 16 |
| T-PLG-07 | CPU loop, ngủ/chờ, memory growth, spawn child và output vượt 1 MiB | Các quota có hiệu lực đúng phạm vi; child không sống ngoài hợp đồng sau kết thúc | PLG-09, 11 |
| T-PLG-08 | Gửi hơn 2 job chạy và hơn 20 job chờ cho một tenant qua nhiều replica; thêm tenant khác | Quota toàn dịch vụ được phối hợp khi đã cam kết; overload/queue có hành vi rõ, tenant khác không bị bỏ đói ngoài policy | PLG-10 |
| T-PLG-09 | Message/output sai schema/version, yêu cầu nạp class hoặc field tự nhận admin; dữ liệu nguy hiểm cho sink thử | Không deserialize/thực thi theo kiểu/lệnh tự khai; host xử lý output như dữ liệu có kiểm tra | PLG-11 |
| T-PLG-10 | Callback giả/replay, mất response sau commit, retry cùng operation và crash | Xác thực/context/state đúng; không thêm tác dụng bị cấm, kết quả chưa rõ đi đối soát | PLG-11, 12 |
| T-PLG-11 | Commit revoke rồi dùng grant/cache cũ ở mọi broker/replica | Chậm nhất T0 + 30 giây không broker nào chấp nhận operation mới trong phạm vi thu hồi | PLG-06, 14 |
| T-PLG-12 | Sau revoke, parent treo và child giữ hoạt động; instance mất liên lạc điều phối | Nhóm thực thi bị dừng chậm nhất T0 + 60 giây theo thiết kế; xác nhận thực tế, không chỉ cờ disabled | PLG-09, 14 |
| T-PLG-13 | Update cùng plugin ID nhưng xin thêm quyền/mạng hoặc đổi hook/dependency | Giữ staging hoặc từ chối cho tới khi đánh giá/phê duyệt đúng digest và quyền | PLG-03, 13 |
| T-PLG-14 | Rollback/restore tới digest bị chặn hoặc snapshot chứa epoch/grant cũ | Không khởi động bằng quyền đã thu hồi; đối chiếu policy hiện hành trước kích hoạt | PLG-15, 18 |
| T-PLG-15 | Plugin cố đưa secret/input nhạy cảm vào log/output; thử đọc kết quả tenant khác | Kênh được host quản lý không rò dữ liệu trái policy; audit đủ truy vết mà không công bố token | PLG-11, 16 |
| T-PLG-16 | Broker/policy store/sandbox setup lỗi hoặc state thu hồi quá tuổi | Không chuyển sang chạy đặc quyền/in-process hoặc bỏ kiểm tra; degraded mode đúng phạm vi | PLG-14, 17 |
| T-PLG-17 | Diễn tập publisher bị chiếm, cần thu hồi nhiều digest/instance và đối soát job đang chạy | Xác định đúng phạm vi, giữ bằng chứng và phục hồi không làm sống lại mã/quyền bị chặn | PLG-14, 15, 18 |
| T-PLG-18 | Plugin đúng nguồn/digest/quyền, context hợp lệ, dữ liệu và tài nguyên trong giới hạn | Job hợp lệ hoàn thành; broker chỉ trả dữ liệu cho phép, audit liên kết đúng plugin/tenant/job | PLG-01, 05, 06, 07, 09, 16 |

### 13.1. Acceptance criteria theo Given–When–Then

**AC-01 — Plugin hợp lệ chạy với dữ liệu tối thiểu.** Given `demo-report` đúng digest đã được phê duyệt, runtime đạt chính sách và context cho phép đọc summary của tối đa 100 order. When job được thực thi. Then broker chỉ trả các order/field được phép, output đúng schema/kích thước và audit liên kết đúng tenant/job. Credential database hoặc file host không được cung cấp cho plugin. Một hệ thống từ chối mọi plugin không được coi là đạt chỉ vì test âm tính đều bị chặn.

**AC-02 — Không tăng quyền bằng manifest hoặc đầu ra.** Given plugin đang được cấp `orders.readSummary`. When nó gọi `orders.write`, gửi tenant khác, tự thêm field admin hoặc trả một lệnh quản trị trong output. Then không có tác dụng/đọc dữ liệu trái quyền. Khi version mới xin thêm operation, Then quyền mới không được tự kế thừa từ approval của version cũ.

**AC-03 — Thu hồi có bằng chứng thời gian.** Given instance và grant cũ đang hoạt động trên nhiều replica. When quyết định revoke được commit tại T0. Then operation mới bị chặn ở mọi broker chậm nhất T0 + 30 giây và nhóm thực thi dừng chậm nhất T0 + 60 giây. Bằng chứng gồm thời điểm commit, quyết định broker, trạng thái process/child thực tế và job cần đối soát; không chỉ ảnh chụp nút disabled.

**AC-04 — Quota và lỗi không mở đặc quyền.** Given plugin thử CPU loop, cấp phát, spawn child hoặc chờ quá deadline. When nó vượt từng giới hạn đã định. Then runtime cưỡng chế xử lý theo hợp đồng, host không đọc output vô hạn và không đổi sang chạy cùng quyền host để hoàn thành job. Lỗi của policy store cũng không làm grant trở thành được phép vô thời hạn.

**AC-05 — Phục hồi giữ chính sách hiện hành.** Given một digest hoặc publisher đã bị thu hồi và có snapshot cấu hình/grant trước sự cố. When rollback/restore. Then host kiểm tra policy/epoch hiện hành, không nhận job bằng quyền cũ và chỉ kích hoạt nội dung/quyền được duyệt lại. Tác dụng đã commit trước điểm chặn được xác định/đối soát riêng, không tuyên bố đã tự hoàn tác.

### 13.2. Bằng chứng và giới hạn kiểm thử

Lưu phiên bản host/runtime, artifact digest, manifest/approval, policy revision/epoch, cấu hình cách ly có hiệu lực, topology replica, fixture plugin, grant/context thử, các mốc thời gian và tác dụng/không có tác dụng ở hệ thống đích.

Với ranh giới cách ly, cần quan sát quyền/file/network/process thực tế. Với revoke, phải thử cả broker cache cũ, callback và instance bị mất liên lạc. Với retry, cần đối chiếu trạng thái nghiệp vụ thay vì chỉ HTTP response hoặc log plugin.

Test thành công trong một cấu hình không tự chứng minh mọi loại plugin an toàn, đặc biệt khi cho phép native code hoặc thay đổi quyền nền tảng. Khi đổi runtime, mô hình process, network, grant, loader hoặc hook, phải kiểm tra lại những bảo đảm liên quan.

## 14. Truy vết qua vòng đời phát triển

```text
Mục tiêu mở rộng chức năng mà không trao quyền host ngoài nhu cầu
  → PLR-xx: mã bị thay, vượt grant, cross-tenant, đường vòng, DoS, revoke sai
  → PLG-xx: phạm vi + điều kiện đạt + owner + hành vi khi không đạt
  → Registry/loader + runtime cách ly + broker + policy/grant + audit
  → T-PLG-xx và AC-xx
  → Quan sát, update, thu hồi, đối soát và phục hồi
```

| Quyết định | Yêu cầu | Kiểm chứng tiêu biểu |
| --- | --- | --- |
| Nội dung/nguồn bất biến và cài đặt chưa thực thi | PLG-01, 02, 03, 04 | T-PLG-01, 02, 03 |
| Cách ly và không có ambient privilege | PLG-05, 08, 09 | T-PLG-05, 06, 07; AC-04 |
| Grant/context/object-level ở broker | PLG-06, 07 | T-PLG-04, 06, 18; AC-01, 02 |
| Input/output, callback và tác dụng có kiểm soát | PLG-11, 12 | T-PLG-09, 10; AC-02 |
| Update/revoke/rollback theo policy hiện hành | PLG-13, 14, 15 | T-PLG-11, 12, 13, 14; AC-03, 05 |
| Lỗi không mở đặc quyền và có bằng chứng phục hồi | PLG-16, 17, 18 | T-PLG-15, 16, 17 |

Khi thêm permission, hook, khả năng mạng, mã native, nguồn cập nhật hoặc cơ chế tái sử dụng worker, cần xem lại threat model và test liên quan. Một thay đổi trông như “chỉ thêm chức năng plugin” có thể thay đổi ranh giới quyền hoặc dữ liệu.

## 15. Lỗi thường gặp và bài tập áp dụng

| Cách làm | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| “Plugin có chữ ký nên chạy với quyền host được.” | Chữ ký không chứng minh mã vô hại hoặc quyền cần thiết | Xác thực nguồn, phê duyệt quyền và chọn ranh giới thực thi |
| “Classloader riêng là sandbox.” | Chưa tách quyền tiến trình hay mọi khả năng của mã | Nêu mức tin cậy và dùng cơ chế cách ly đáp ứng mô hình đe dọa |
| “Manifest không xin mạng nên không có mạng.” | Manifest không tự cưỡng chế network | Network policy/egress thực tế và kiểm thử đường vòng |
| “Tenant do plugin gửi là tenant của job.” | Plugin có thể tự đổi phạm vi | Context từ host và kiểm tra object-level tại broker |
| “Tắt plugin nghĩa là grant đã hết quyền.” | Instance/cache/callback có thể còn hoạt động | Deadline thu hồi, kiểm tra mỗi operation và dừng nhóm thực thi |
| “Hủy future đã dừng plugin.” | Mã/child hoặc tác dụng ngoài có thể tiếp tục | Cưỡng chế runtime và đối soát phần đã được chấp nhận |
| “Version mới giữ nguyên quyền cũ và thêm quyền mới tự động.” | Mở rộng phạm vi mà chưa được duyệt | Diff quyền, phê duyệt theo digest và cấp grant đúng bản |
| “Process riêng nên không đọc được secret.” | Vẫn có thể kế thừa environment, mount hoặc danh tính rộng | Kiểm tra quyền môi trường thực tế và tối thiểu dữ liệu |
| “Output parse được thì dùng làm lệnh cho host.” | Dữ liệu từ plugin chưa tạo quyền quản trị | Schema/ngữ nghĩa, xử lý sink và policy tại tác dụng |

Một host cho plugin chạy cùng JVM, truyền đối tượng service có credential quản trị và lấy tenant từ body callback. Manifest chỉ liệt kê quyền đọc nhưng plugin có thể truy cập mạng tùy ý. Update được tự động nạp theo version mới nhất; khi incident, đội chỉ tắt nút trên giao diện và rollback cấu hình cũ.

Hãy thực hiện:

1. Nêu ít nhất sáu kịch bản đe dọa và tài sản/bất biến bị ảnh hưởng.
2. Chọn mô hình tin cậy/cách ly và giải thích plugin có thể tiếp cận những khả năng nào.
3. Viết sáu yêu cầu có ID, owner, điều kiện đạt, hành vi lỗi và bằng chứng.
4. Thiết kế broker cho một operation hẹp, với caller, grant, tenant/job và object-level.
5. Nêu các test chứng minh plugin không có đường vòng qua credential, mạng hoặc filesystem.
6. Thiết kế ngân sách quota và thu hồi xuyên các replica, instance, child và callback.
7. Giải thích cách upgrade/rollback và xử lý tác dụng đã xảy ra mà không làm sống lại quyền cũ.

Trước khi chấp nhận đặc tả, kiểm tra:

- Plugin/publisher/digest, dependency, hook và owner đã rõ chưa?
- Kiểm chứng nội dung và phê duyệt quyền có phân biệt chưa?
- Cách ly có được nền tảng cưỡng chế hay chỉ là một lời khai trong manifest?
- Caller, context, grant, object-level và trạng thái thu hồi có được broker xác minh không?
- Plugin có nhận ambient credential, handle, filesystem hoặc mạng ngoài nhu cầu không?
- Quota, hàng chờ, output và process tree có phạm vi/điểm thực thi rõ không?
- Callback, retry và kết quả chưa rõ có idempotency/đối soát phù hợp không?
- Update có kiểm tra quyền mới, revoke có thời hạn và rollback có xét policy hiện hành không?
- Audit và phục hồi có đủ bằng chứng mà không làm lộ dữ liệu tenant/secret không?

Một cơ chế plugin đạt yêu cầu khi host giữ được quyền quyết định tại đúng ranh giới, còn mã mở rộng chỉ nhận dữ liệu và khả năng đã được phê duyệt trong thời gian cần thiết.
