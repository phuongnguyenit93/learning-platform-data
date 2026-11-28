# License và security review

## 1. Hai quyết định cần được đặc tả riêng

Trong chương **Dependency và supply chain**, license review và security review giúp tổ chức quyết định có thể đưa một thành phần vào sản phẩm theo cách sử dụng dự kiến hay không.

Hai hoạt động cùng dùng thông tin về dependency, nhưng trả lời những câu hỏi khác nhau:

- **License review:** có bằng chứng về quyền sử dụng nào, điều kiện nào áp dụng và tổ chức có thực hiện được các nghĩa vụ liên quan không?
- **Security review:** việc sử dụng đúng thành phần này trong kiến trúc cụ thể tạo ra rủi ro gì, kiểm soát nào cần có và ai chấp nhận phần rủi ro còn lại?

Một dependency có license được chấp nhận vẫn có thể chứa mã độc hoặc lỗ hổng nghiêm trọng. Một dependency không có cảnh báo bảo mật vẫn có thể thiếu bằng chứng về quyền phân phối.

Trong module đặc tả yêu cầu bảo mật, mục tiêu không dừng ở việc tạo hai ô đánh dấu. Cần chuyển kết quả review thành những điều kiện có thể thực thi và kiểm chứng:

**Thành phần và bằng chứng → cách sử dụng → yêu cầu license và rủi ro bảo mật → quyết định theo từng chiều → điều kiện phát hành → theo dõi thay đổi.**

Sau bài học, người học có thể:

- Xác định hồ sơ review gắn với phiên bản, digest và ngữ cảnh sử dụng.
- Phân biệt license được khai báo, thông tin công cụ tìm thấy và kết luận có thẩm quyền.
- Biểu diễn license expression, lựa chọn license và nghĩa vụ cần thực hiện.
- Đánh giá bảo mật ngoài việc đếm CVE hoặc nhìn một điểm số.
- Viết yêu cầu cho review, ngoại lệ, gate phát hành, audit và tái đánh giá.
- Tạo tiêu chí kiểm thử chứng minh quyết định được áp dụng trên artifact thực tế.

Các tên package, trạng thái, thời hạn và schema trong bài thuộc một tình huống minh họa. Chúng không phải kết luận về một sản phẩm thật hoặc một policy pháp lý áp dụng chung.

## 2. Mô hình quyết định: license đạt không thay cho security đạt

### 2.1. Đầu ra cần giữ riêng từng chiều

Một hồ sơ có thể dùng các trạng thái nội bộ sau:

| Chiều | Trạng thái minh họa | Ý nghĩa |
|---|---|---|
| License | APPROVED | Quyền và điều kiện đã được xác nhận cho phạm vi sử dụng được nêu |
| License | APPROVED_WITH_CONDITIONS | Chấp nhận theo kết luận đã ghi, nhưng còn điều kiện phải thực hiện tại mốc quy định |
| License | NEEDS_CLARIFICATION | Thiếu hoặc mâu thuẫn bằng chứng để kết luận |
| License | REJECTED_FOR_SCOPE | Cách dùng đề nghị không đáp ứng quyền hoặc điều kiện đã xác định |
| Security | ACCEPTABLE | Đáp ứng baseline trong ngữ cảnh và thời điểm đánh giá |
| Security | ACCEPTABLE_WITH_CONTROLS | Cần các kiểm soát cụ thể và bằng chứng chúng có hiệu lực |
| Security | NEEDS_ANALYSIS | Chưa đủ thông tin về hiện diện, tác động hoặc nguồn thành phần |
| Security | UNACCEPTABLE | Không đáp ứng policy hoặc có rủi ro chưa được chấp nhận đúng thẩm quyền |

Các tên này là trạng thái của quy trình minh họa, không phải enum chuẩn SPDX hoặc kết quả mặc định của một công cụ.

Trạng thái tổng hợp còn phải xét điều kiện đến hạn, bằng chứng còn hiệu lực và việc artifact phát hành có đúng subject đã xét không.

### 2.2. Một số tổ hợp cần xử lý

| License review | Security review | Kết quả cho phạm vi phát hành đang xét |
|---|---|---|
| Đã chấp nhận và nghĩa vụ đến hạn đã hoàn tất | Đáp ứng baseline, kiểm soát bắt buộc đã có | Có thể đi tiếp nếu các gate khác cũng đạt |
| Đã chấp nhận | Rủi ro chưa được chấp nhận hoặc thiếu phân tích bắt buộc | Chưa phát hành |
| Thiếu bằng chứng về quyền sử dụng | Không có cảnh báo đã biết trong nguồn được kiểm tra | Chưa phát hành; kết quả scanner không giải quyết thiếu quyền |
| Có điều kiện phải đưa notice vào gói, chưa thực hiện | Security đạt | Chưa phân phối gói đó |
| Đã chấp nhận cho ứng dụng nội bộ | Đạt trong ngữ cảnh cũ | Cần xem lại khi chuyển sang phân phối cho khách hàng |

Không dùng điểm trung bình để bù trừ hai chiều. Một điểm bảo mật cao không xóa nghĩa vụ license; license thuận lợi không làm giảm tác động của một đường thực thi mã bị khai thác.

Người có quyền chấp nhận rủi ro bảo mật nội bộ cũng không tự tạo quyền sử dụng phần mềm mà tổ chức chưa được cấp. Nếu cần quyền khác, phải có bằng chứng hợp lệ về quyền đó hoặc thay đổi cách dùng/thành phần.

## 3. Xác định phạm vi và hồ sơ đầu vào

### 3.1. Review thành phần cụ thể, không chỉ tên dự án

Một hồ sơ tối thiểu cần có:

| Nhóm thông tin | Nội dung cần xác định |
|---|---|
| Định danh | Ecosystem, namespace, tên, version/revision và biến thể |
| Nội dung | Digest của artifact được xét; nguồn tải và bằng chứng nguồn |
| Quan hệ | Dependency trực tiếp/bắc cầu; thành phần cha; code nhúng hoặc đã sửa |
| Vị trí sử dụng | Build, test, packaged, runtime, plugin hoặc agent |
| Sản phẩm | Dịch vụ, release, owner và liên kết inventory |
| Ngữ cảnh quyền sử dụng | Nội bộ, cung cấp qua dịch vụ, phân phối binary/source, SDK hoặc gói khách hàng |
| Thay đổi kỹ thuật | Sửa code, linking, shading, sinh mã, đóng gói lại và chuyển giao |
| Dữ liệu và quyền | Dữ liệu thành phần tiếp cận, quyền thực thi, network và ranh giới tenant |
| Bằng chứng license | License text của đúng release, notice, điều khoản kèm theo hoặc thỏa thuận liên quan |
| Bằng chứng bảo mật | Advisory, kết quả phân tích, provenance/signature khi có và cấu hình sử dụng |
| Phiên bản đánh giá | Policy, công cụ, nguồn dữ liệu, thời gian và người có thẩm quyền |

Hai artifact cùng tên/version nhưng digest khác nhau không được tự thừa hưởng cùng quyết định. Hai cách dùng cùng byte artifact cũng có thể cần quyết định khác vì phạm vi quyền và rủi ro khác nhau.

### 3.2. Phạm vi không chỉ có dependency trực tiếp

Review cần xem xét dependency bắc cầu và các thành phần được đóng gói cùng sản phẩm: native library, code sao chép, thư viện nhúng, tài nguyên web hoặc package trong image thuộc phạm vi phát hành.

Công cụ build và test cũng có thể xử lý source, secret pipeline hoặc tạo nội dung đầu ra. Việc không nằm trong production artifact không đồng nghĩa không có rủi ro hoặc không cần xem xét điều kiện sử dụng.

Không suy ra cùng một nghĩa vụ cho mọi thành phần chỉ từ nhãn build/runtime. Nghĩa vụ phụ thuộc license thực tế, cách tương tác, nội dung được đưa vào đầu ra và cách sản phẩm được cung cấp.

OWASP SCVS coi component trực tiếp và bắc cầu đều là đối tượng phân tích; các khía cạnh gồm lỗ hổng, tình trạng phiên bản, chức năng và license. [OWASP SCVS: Component Analysis](https://scvs.owasp.org/scvs/v5-component-analysis/)

### 3.3. Rủi ro cần được truy vết

| Mã rủi ro | Tình huống | Hệ quả cần ngăn |
|---|---|---|
| R-LSR-01 | Tin nhãn license sai hoặc thiếu thông tin của release thực tế | Dùng hoặc phân phối ngoài điều kiện được xác nhận |
| R-LSR-02 | Chấp nhận license nhưng bỏ nghĩa vụ khi đóng gói | Release không có tài liệu hoặc nội dung bắt buộc |
| R-LSR-03 | Review một artifact, phát hành artifact khác | Kết luận không áp dụng cho nội dung thực tế |
| R-LSR-04 | Xem không có CVE như bằng chứng an toàn | Bỏ qua mã độc, nguồn bị thay, cấu hình nguy hiểm hoặc khoảng trống dữ liệu |
| R-LSR-05 | Không đánh giá quyền và dữ liệu của component | Rủi ro ảnh hưởng rộng hơn dự kiến |
| R-LSR-06 | Dùng lại approval khi đổi cách cung cấp hoặc kiến trúc | Quyền, nghĩa vụ và kiểm soát không còn phù hợp |
| R-LSR-07 | Ngoại lệ không có phạm vi, thời hạn hoặc thẩm quyền | Bỏ kiểm soát kéo dài hoặc áp dụng sai đối tượng |
| R-LSR-08 | Quyết định/bằng chứng bị sửa hoặc mất lịch sử | Không điều tra hoặc tái đánh giá được |

## 4. License review: từ dữ liệu nhận diện tới nghĩa vụ có bằng chứng

### 4.1. Tách khai báo, phát hiện và kết luận

Một package có thể có metadata registry ghi license A, file LICENSE ghi A hoặc B, còn một phần code vendored có notice riêng. Không chọn thông tin thuận lợi nhất rồi bỏ phần còn lại.

Cần giữ riêng:

- Nhà cung cấp hoặc package khai báo điều gì.
- Công cụ đã tìm thấy những text/header nào và ở đâu.
- Người có thẩm quyền kết luận điều gì, dựa vào bằng chứng nào.
- Tổ chức chọn nhánh nào nếu có quyền lựa chọn thực sự.
- Các nghĩa vụ nào được chuyển thành điều kiện vận hành hoặc phát hành.

SPDX 2.3.1 phân biệt license được khai báo và license được người tạo tài liệu kết luận. Với các field liên quan, NONE và NOASSERTION có nghĩa được đặc tả riêng; không được hiểu chúng như một license cho phép tự do. [SPDX 2.3.1: Package information](https://spdx.github.io/spdx-spec/v2.3.1/package-information/)

Nếu không có bằng chứng đủ về quyền sử dụng, trạng thái của quy trình là cần làm rõ. Repository công khai, package tải miễn phí hoặc tên file “open-source” không tự tạo kết luận.

Bằng chứng cần gắn đúng release/commit và artifact. License text trên trang hiện tại của dự án không được tự gán ngược cho mọi version cũ. Khi có mâu thuẫn, lưu cả nguồn và chuyển đến người có trách nhiệm xác nhận.

### 4.2. Đọc license expression đúng cấu trúc

SPDX license expression có các toán tử thể hiện quan hệ giữa điều kiện license. Các ví dụ bên dưới minh họa cú pháp, không khẳng định một package cụ thể được cấp theo những biểu thức này. [SPDX 2.3.1: License expressions](https://spdx.github.io/spdx-spec/v2.3.1/SPDX-license-expressions/)

| Biểu thức minh họa | Điều cần giữ trong hồ sơ review |
|---|---|
| `MIT` | License đã nhận diện và bằng chứng áp dụng |
| `MIT OR Apache-2.0` | Có lựa chọn giữa các nhánh; ghi nhánh được chọn nếu thực sự được cấp lựa chọn |
| `MIT AND Apache-2.0` | Các điều kiện cùng áp dụng; không tự bỏ một nhánh |
| `GPL-2.0-only WITH Classpath-exception-2.0` | License đi cùng exception; phải xét nội dung exception áp dụng |
| `LicenseRef-Vendor-Terms` | Có điều khoản được tham chiếu riêng, cần text và kết luận phù hợp |
| `(MIT OR Apache-2.0) AND LicenseRef-Asset-Terms` | Giữ cấu trúc nhóm và cả điều kiện bổ sung |

Không gom hai license công cụ tìm thấy thành OR nếu chưa có bằng chứng rằng đó là quyền lựa chọn. Chúng có thể áp dụng cho các file khác nhau hoặc cần được tuân thủ đồng thời.

Không kiểm tra expression bằng cách tìm substring trong allowlist. Parser và policy phải hiểu đúng cấu trúc theo phiên bản định dạng đã chọn; dữ liệu sai cú pháp hoặc reference thiếu text không được tự chuyển thành approved.

Nếu chọn một nhánh trong OR, vẫn giữ expression được cấp ban đầu và lý do/lựa chọn đã xác nhận. Không sửa lịch sử để làm như chỉ một license từng tồn tại.

### 4.3. Chuyển kết luận thành nghĩa vụ kiểm chứng được

Review không kết thúc ở nhãn “permissive” hay “copyleft”. Đầu ra phải nói tổ chức cần làm gì trong cách dùng đang xét.

Ví dụ, MIT có điều kiện giữ copyright notice và permission notice trong các bản sao hoặc phần đáng kể thuộc phạm vi license. Một yêu cầu kỹ thuật có thể là gói phân phối phải chứa đúng notice đã đối chiếu với thành phần được đưa vào. [OSI: The MIT License](https://opensource.org/license/mit)

Apache-2.0 có các điều kiện tại phần Redistribution, gồm cung cấp bản license, thông báo về file sửa đổi và xử lý attribution từ NOTICE khi điều kiện đó áp dụng. Không biến ví dụ này thành một checklist đầy đủ thay cho đọc điều khoản và xác nhận theo cách phân phối thực tế. [Apache License 2.0, mục 4](https://www.apache.org/licenses/LICENSE-2.0)

Hồ sơ nghĩa vụ có thể dùng cấu trúc:

| Thành phần nghĩa vụ | Ví dụ yêu cầu nội bộ |
|---|---|
| Nội dung phải cung cấp | Bản license, notice hoặc tài liệu khác theo kết luận |
| Phạm vi | Component, file, gói khách hàng và hình thức phân phối |
| Thời điểm | Trước phân phối hoặc trong suốt thời gian cung cấp theo điều kiện được xác nhận |
| Nơi thực hiện | Thư mục third-party notices, tài liệu đi kèm hoặc kênh được kết luận cho phép |
| Owner | Đội chịu trách nhiệm tạo và duy trì |
| Bằng chứng | Digest/tài liệu của gói cuối, vị trí nội dung và kết quả kiểm tra |
| Điều kiện thay đổi | Component đổi, sửa code, đổi hình thức cung cấp hoặc kết luận được cập nhật |

Đối với nghĩa vụ có tính tiếp diễn, cần có kiểm soát duy trì sau phát hành, không chỉ một ảnh chụp “đã hoàn tất”. Nếu nghĩa vụ đòi hỏi năng lực cung cấp nội dung khi có yêu cầu, phải kiểm chứng được năng lực và thời hạn tương ứng.

Không kết luận toàn bộ dịch vụ qua mạng đều được miễn nghĩa vụ, cũng không coi mọi cách linking đều tạo cùng kết quả. Những trường hợp này cần thông tin kỹ thuật và kết luận về đúng điều khoản áp dụng.

### 4.4. Tương thích là vấn đề của cả tổ hợp và cách cung cấp

License được policy cho phép riêng lẻ chưa chứng minh mọi tổ hợp đều phù hợp. Kết luận cần xét các thành phần cùng được cung cấp, phần đã sửa, cách kết hợp và điều kiện mà tổ chức đã xác nhận có thể thực hiện.

Nếu có quyền dùng theo hợp đồng thương mại riêng, cần lưu tham chiếu đến bằng chứng có thẩm quyền, phạm vi sản phẩm, version, thời hạn và điều kiện. Không coi câu “đã mua” trong ticket là đủ cho mọi cách phân phối.

## 5. Security review: đánh giá component trong kiến trúc thực tế

### 5.1. Không chỉ kiểm tra CVE

| Khía cạnh | Câu hỏi review | Bằng chứng phù hợp |
|---|---|---|
| Định danh và nguồn | Có đúng package, version, digest và nhà cung cấp dự kiến không? | Inventory, nguồn artifact, chữ ký/provenance đã xác minh theo policy |
| Lỗ hổng đã biết | Advisory nào áp dụng cho nội dung và nền tảng này? | Dữ liệu advisory có thời điểm, đối chiếu version/distro và kết quả phân tích |
| Khả năng ảnh hưởng | Luồng có xử lý đầu vào tấn công hoặc dùng chức năng liên quan không? | Data flow, cấu hình, kiểm thử và phân tích có giới hạn rõ |
| Quyền | Component có quyền đọc secret, dữ liệu tenant hoặc thực thi lệnh gì? | Kiến trúc quyền, runtime policy và phép thử từ chối |
| Giao tiếp | Có tải code, telemetry hoặc gửi dữ liệu ra ngoài không? | Cấu hình egress, hành vi được kiểm tra và hợp đồng dữ liệu |
| Vòng đời hỗ trợ | Có kênh nhận bản vá và khả năng nâng cấp/thay thế không? | Policy hỗ trợ, lịch sử xử lý và kế hoạch bảo trì |
| Tích hợp | Cấu hình mặc định, plugin, deserialization hay parser có làm tăng bề mặt tấn công không? | Threat model và cấu hình triển khai |
| Build/install | Mã bên thứ ba có chạy trong môi trường chứa credential pipeline không? | Quyền job, sandbox, đường lấy dependency và kiểm soát cài đặt |
| Vận hành | Có phát hiện bất thường và phục hồi được không? | Metric/log được lọc, quy trình cô lập, rollback và dữ liệu khôi phục |

Không có cảnh báo nghĩa là chưa tìm thấy cảnh báo trong phạm vi nguồn và phương pháp đã dùng, không phải chứng nhận an toàn. Một thành phần bị cài mã độc có thể chưa có CVE; một package ký hợp lệ có thể vẫn đến từ nguồn đã bị chiếm.

Một version mới không tự tốt hơn trong mọi trường hợp. Review phải xác nhận nội dung, tương thích và rủi ro thay đổi thay vì chỉ chọn nhãn “latest”.

### 5.2. Điểm nghiêm trọng là đầu vào, không phải toàn bộ quyết định

CVSS mô tả các đặc tính và mức nghiêm trọng của lỗ hổng. FIRST nêu việc bổ sung thông tin Threat và Environmental theo cách sử dụng để hỗ trợ đánh giá trong bối cảnh cụ thể. [FIRST: CVSS v4.0 specification](https://www.first.org/cvss/v4.0/specification-document)

Policy review có thể xét thêm mức tiếp xúc, dữ liệu bị ảnh hưởng, đặc quyền, bằng chứng khai thác, kiểm soát bù, tình trạng bản vá và khả năng phục hồi.

Không hạ rủi ro chỉ vì một phép phân tích tĩnh không tìm được đường gọi. Dynamic loading, reflection, plugin hoặc thay đổi cấu hình có thể nằm ngoài khả năng của phương pháp đó.

Nếu kết luận “không bị ảnh hưởng” được dùng để cho phát hành, phải lưu lý do, bằng chứng, phạm vi và điều kiện làm kết luận hết hiệu lực. Không xóa finding gốc để làm báo cáo trông sạch.

### 5.3. Kiểm soát bù phải có điều kiện đo được

Ví dụ, một parser có rủi ro khi xử lý đầu vào không tin cậy. Quyết định cho phép tạm thời có thể yêu cầu:

- Chỉ nhận định dạng và kích thước đã được giới hạn.
- Chạy trong process riêng với quyền tối thiểu.
- Không có đường truy cập secret hoặc egress không cần thiết.
- Có timeout và cận tài nguyên.
- Có bằng chứng kiểm thử chính luồng dữ liệu triển khai.
- Có owner, hạn thay thế/bản vá và điều kiện tái đánh giá.

Các kiểm soát này chỉ có giá trị nếu kiến trúc thực thi được và phù hợp cơ chế lỗi. Không gắn nhãn “có WAF” hoặc “mạng nội bộ” rồi coi mọi đường tấn công đã bị loại bỏ.

## 6. Chuyển review thành bộ yêu cầu cụ thể

### 6.1. Một yêu cầu đầy đủ

**LSR-01 — Chỉ phát hành artifact đã đáp ứng cả hai chiều review**

- **Rủi ro:** R-LSR-01, R-LSR-02, R-LSR-03 và R-LSR-04.
- **Phạm vi:** mọi artifact phân phối cho khách hàng của dịch vụ tài liệu trong pipeline được quản lý.
- **Điều kiện:** sau khi đóng gói hoàn tất, trước promote hoặc phân phối.
- **Yêu cầu:** hệ thống phải xác nhận quyết định license và security áp dụng cho đúng component, artifact và ngữ cảnh cung cấp.
- **Điều kiện bổ sung:** nghĩa vụ đến hạn và kiểm soát bắt buộc phải có bằng chứng đã thực hiện; điều kiện tiếp diễn phải có cơ chế duy trì đã được chấp nhận.
- **Khi thiếu hoặc không hợp lệ:** chưa cho artifact đi qua gate; trả mã lý do có thể đối chiếu, không gom thành “scanner error”.
- **Bằng chứng:** subject digest, inventory revision, usage profile, quyết định theo từng chiều, policy revision và các evidence reference.
- **Tiêu chí chấp nhận:** security đạt nhưng thiếu notice bắt buộc vẫn bị chặn; license đạt nhưng security chưa đủ dữ liệu bắt buộc cũng bị chặn.
- **Giới hạn:** gate này không tự thay các yêu cầu khác về chữ ký, kiểm thử hay quyền triển khai.

### 6.2. Các yêu cầu bổ sung

| ID | Hành vi bắt buộc trong ví dụ | Tiêu chí chấp nhận chính |
|---|---|---|
| LSR-02 | Component trực tiếp, bắc cầu và thành phần nhúng thuộc phạm vi phải có hồ sơ review hoặc khoảng trống được quản lý rõ. | Một thư viện bắc cầu hoặc file thêm thủ công không được bị bỏ qua rồi báo toàn bộ đạt. |
| LSR-03 | Hồ sơ nhận diện đúng version, digest và nguồn; quyết định không áp dụng chung theo tên package. | Hai artifact cùng nhãn nhưng khác nội dung không tự dùng chung approval. |
| LSR-04 | Dữ liệu khai báo, kết quả phát hiện và kết luận license được giữ riêng với bằng chứng. | Metadata registry mâu thuẫn file trong gói tạo trạng thái cần xác nhận, không chọn âm thầm một nguồn. |
| LSR-05 | Expression được xử lý theo cú pháp/phiên bản đã chọn; lựa chọn OR và điều kiện AND/WITH không bị làm mất. | OR không tự xuất hiện từ hai text rời; AND không bị rút còn một license được phép. |
| LSR-06 | Mỗi nghĩa vụ có scope, owner, mốc thực hiện và bằng chứng kiểm chứng. | Gói cuối thiếu nội dung bắt buộc không qua gate, dù hồ sơ đã được chấp nhận có điều kiện. |
| LSR-07 | Security review xét định danh, nguồn, cảnh báo, quyền, dữ liệu, cấu hình và vòng đời theo mức rủi ro. | Không dùng báo cáo không có CVE làm điều kiện duy nhất để nhận component có quyền cao. |
| LSR-08 | Kết luận không bị ảnh hưởng hoặc false positive có lý do, bằng chứng và điều kiện tái đánh giá. | Finding còn lịch sử; thay đổi cấu hình liên quan làm kết luận được xem lại. |
| LSR-09 | Phê duyệt phải do role được cấp cho đúng chiều quyết định; người đề nghị không tự sửa kết quả qua dữ liệu đầu vào. | Tài khoản chỉ có quyền security không tạo hoặc giả kết luận về quyền phân phối. |
| LSR-10 | Ngoại lệ chỉ áp dụng theo policy, phạm vi, thời hạn và điều kiện đã ghi. | Ngoại lệ cho một digest hoặc deployment không bao phủ version/môi trường khác; hết hạn không tự gia hạn. |
| LSR-11 | Thay component, cách cung cấp, license evidence, threat data hoặc kiến trúc liên quan phải kích hoạt tái đánh giá phù hợp. | Chuyển từ nội bộ sang gói khách hàng không kế thừa vô điều kiện approval cũ. |
| LSR-12 | Gate phân biệt thiếu dữ liệu, vi phạm policy và chấp nhận có điều kiện; không fallback cho phép khi công cụ lỗi. | Scanner không chạy hoặc nguồn quá hạn không xuất thành “0 finding, approved”. |
| LSR-13 | Quyết định, ngoại lệ và bằng chứng có version, audit, kiểm soát truy cập và lịch sử. | Sửa kết luận tạo revision mới; không xóa finding hoặc thay file bằng chứng rồi giữ kết quả cũ. |
| LSR-14 | Có thể truy từ component/finding/nghĩa vụ tới release, deployment và owner liên quan. | Khi cần thu hồi, truy vấn trả đúng artifact đang được dùng và phần chưa được xác nhận. |

Các mã LSR là định danh của bài học. Mỗi yêu cầu trong dự án cần liên kết đến rủi ro, thành phần kiến trúc, ca kiểm thử và người chịu trách nhiệm.

## 7. Hồ sơ review và bằng chứng của gói phát hành

### 7.1. Ví dụ bản ghi có điều kiện chưa hoàn tất

Schema sau do bài học tự định nghĩa. Tên package và digest lặp là dữ liệu mẫu; nó không phải tài liệu SPDX chuẩn hay kết luận về package thật.

```yaml
reviewId: "review-documents-sdk-208"
revision: 1

component:
  purl: "pkg:maven/com.example/report-sdk@2.4.0"
  artifactSha256: "1111111111111111111111111111111111111111111111111111111111111111"

usage:
  profileId: customer-binary-distribution-v2
  product: documents-service
  modified: false
  packagedInCustomerDelivery: true

targetRelease:
  id: "documents-service-1.8.0"
  artifactSha256: "2222222222222222222222222222222222222222222222222222222222222222"
  inventoryRevision: "inventory-208-r1"

licenseReview:
  offeredExpression: "MIT OR Apache-2.0"
  selectedExpression: "Apache-2.0"
  evidenceRef: "license-evidence-sdk-240"
  decision: APPROVED_WITH_CONDITIONS
  decisionRef: "license-decision-77"
  obligations:
    - id: "obligation-delivery-notices"
      dueAt: before-customer-distribution
      ownerTeam: release-engineering
      status: PENDING
      evidenceRef: null

securityReview:
  decision: ACCEPTABLE_WITH_CONTROLS
  decisionRef: "security-decision-93"
  assessmentRef: "assessment-sdk-240-r3"
  requiredControls:
    - id: parser-isolation
      status: VERIFIED
      evidenceRef: "isolation-check-208"

releaseGate:
  result: BLOCKED
  reasonCodes:
    - LICENSE_OBLIGATION_PENDING

policyRevision: "dependency-review-policy-042"
```

Ví dụ giả định quyền lựa chọn license đã có bằng chứng. Không được tự tạo offeredExpression chỉ vì scanner thấy hai tên license.

Một quyết định có điều kiện không phải gate cho phép ngay. Ở bản ghi này, nghĩa vụ đến hạn trước phân phối chưa có evidence nên release vẫn bị chặn, dù kiểm soát security đã được xác nhận.

### 7.2. Kiểm tra gói cuối thay vì chỉ kiểm tra file nguồn

Giả sử đội phát triển đã thêm thư mục notices vào repository, nhưng cấu hình đóng gói không đưa nó vào gói khách hàng. Kiểm tra source sẽ báo có file; kiểm tra artifact cuối sẽ phát hiện nghĩa vụ chưa được thực hiện.

Bằng chứng phù hợp có thể gồm:

- Subject digest của gói được phân phối.
- Inventory/SBOM có phạm vi được công bố cho gói đó.
- Danh sách nghĩa vụ theo kết luận license.
- Vị trí và nội dung tài liệu thực sự nằm trong gói hoặc kênh được chấp nhận.
- Digest của nội dung bằng chứng và kết quả đối chiếu.
- Kết quả kiểm tra các kiểm soát security còn áp dụng.

Nếu thêm notice làm thay đổi byte gói, đó là digest phát hành mới. Cần cập nhật ràng buộc tới gói cuối, chạy lại các kiểm tra chịu ảnh hưởng và ký theo quy trình đã chọn.

Không nhất thiết lặp lại mọi phân tích thủ công khi một điều kiện đóng gói được sửa. Có thể tái sử dụng phần kết luận còn áp dụng nếu chứng minh input, cách dùng, policy và bằng chứng liên quan không đổi; việc ràng buộc với artifact mới vẫn phải chính xác.

### 7.3. Điều kiện nào phải kiểm tra lại ở runtime?

Một số nghĩa vụ được hoàn tất tại mốc phân phối. Một số điều kiện cần duy trì, như phạm vi sử dụng theo thỏa thuận hoặc khả năng cung cấp nội dung đã được kết luận là cần thiết.

Tương tự, security control như cô lập parser, quyền filesystem và egress cần đúng ở deployment thực tế. Một lần thử trong staging không đủ nếu production có cấu hình khác.

Hồ sơ phải nêu điều kiện nào được đóng tại release, điều kiện nào tiếp diễn và ai theo dõi. Không coi trạng thái VERIFIED là vĩnh viễn trong mọi môi trường.

## 8. Quy trình tự động hóa và các điểm quyết định của con người

### 8.1. Một luồng review theo vòng đời

```text
Đề nghị đưa dependency vào sản phẩm
    -> Xác định component và cách dùng
    -> Thu bằng chứng license/security và đánh dấu khoảng trống
    -> Áp dụng policy, phân loại mức review cần thiết
    -> Kết luận riêng license và security
    -> Thực hiện nghĩa vụ và kiểm soát
    -> Đóng gói, đối soát inventory và kiểm chứng gói cuối
    -> Gate quyết định cho đúng artifact
    -> Phân phối/triển khai và theo dõi điều kiện tiếp diễn
    -> Tái đánh giá khi có thay đổi
```

Những trường hợp đã có policy rõ, input đáng tin và rủi ro phù hợp có thể đi theo luồng tự động. Trường hợp thiếu quyền, điều khoản riêng, mâu thuẫn evidence hoặc quyền thực thi nhạy cảm cần được chuyển tới role có thẩm quyền.

Không mặc định mọi dependency đều cần cùng một cuộc họp, nhưng cũng không cho phép nhãn license phổ biến tự bỏ qua security review.

### 8.2. Mã giả cho gate

```text
evaluateRelease(candidate):
    subject = identifyImmutableArtifact(candidate)
    inventory = requireInventoryBoundTo(subject)
    usage = requireAuthorizedUsageProfile(candidate.product)

    for component in inventory.inScopeComponents:
        dossier = loadApplicableReview(component, usage)

        requireReviewIdentityMatches(dossier, component)
        requireTrustedLicenseConclusion(dossier)
        requireApplicableRightsForUsage(dossier, usage)
        requireDueObligationsSatisfied(dossier, subject)
        requireContinuingObligationsHaveApprovedEnforcement(dossier)

        requireSecurityEvidenceSufficientAndCurrent(dossier)
        requireSecurityDecisionPermitsUsage(dossier, usage)
        requireRequiredControlsVerified(dossier, candidate.deploymentContext)
        requireExceptionsApplicableAndUnexpired(dossier)

    requireInventoryGapsHandledAccordingToPolicy(inventory)
    persistDurableGateDecision(subject, usage, policyRevision)
    return permitFor(subject, usage)
```

Điều kiện ngoại lệ chỉ được dùng khi thực sự có ngoại lệ được policy cho phép. Một hồ sơ không cần ngoại lệ vẫn phải đi qua các kiểm tra bình thường.

Dữ liệu như trạng thái approved, người duyệt và evidenceRef không được tin chỉ vì caller gửi trong request. Gate phải lấy từ nguồn quyết định có thẩm quyền và kiểm tra tính toàn vẹn/liên kết.

### 8.3. Trạng thái lỗi không được biến thành không có finding

Cần phân biệt:

| Trạng thái thu thập | Cách hiểu |
|---|---|
| Hoàn tất, có finding | Có dữ liệu cần đánh giá theo policy |
| Hoàn tất, chưa tìm thấy finding trong phạm vi | Một kết quả có giới hạn theo nguồn, phương pháp và thời điểm |
| Không hoàn tất | Chưa đủ cơ sở để diễn giải kết quả như phân tích hoàn chỉnh |
| Nguồn quá hạn hoặc không rõ độ mới | Chưa đáp ứng yêu cầu về độ mới của dữ liệu |
| Không phân tích được một phần | Có khoảng trống cụ thể cần được ghi và xử lý |

Lệnh scanner trả lỗi nhưng file báo cáo vẫn tồn tại có thể là dữ liệu của lần chạy trước. Phải gắn execution ID, subject, thời điểm và trạng thái hoàn tất, không đọc một file “report.json” bất kỳ rồi coi như kết quả hiện tại.

Quyết định từ cache chỉ được dùng khi còn áp dụng cho đúng input và policy. Mất kết nối nguồn mới không tự làm mới timestamp của dữ liệu cũ.

## 9. Thẩm quyền, điều kiện và ngoại lệ

### 9.1. Chỉ rõ ai quyết định việc gì

| Vai trò | Trách nhiệm minh họa |
|---|---|
| Đội sản phẩm/phát triển | Nêu nhu cầu, cách dùng, sửa đổi và khả năng thay thế |
| Đội quản lý license hoặc người có thẩm quyền pháp lý | Xác nhận quyền/điều kiện cho ngữ cảnh cần xem xét |
| Đội bảo mật và chủ sở hữu rủi ro | Đánh giá rủi ro, xác định kiểm soát và thẩm quyền chấp nhận |
| Đội phát hành | Thực hiện nghĩa vụ đóng gói, xác minh artifact và giữ bằng chứng |
| Đội nền tảng/vận hành | Thực thi runtime control và theo dõi trạng thái triển khai |
| Chủ sở hữu policy | Quản lý tiêu chí, scope tự động hóa và thay đổi quy tắc |

Một tổ chức nhỏ có thể bố trí một người cho nhiều vai trò. Policy cần nói rõ khi nào cần độc lập hoặc nhiều bên xác nhận; không tự dùng nhãn “admin” để cấp mọi quyền.

Tài khoản pipeline nên có quyền đọc kết luận và ghi evidence kỹ thuật trong phạm vi cần thiết. Nó không nên tự chuyển NEEDS_CLARIFICATION thành APPROVED để hoàn tất job.

### 9.2. Chấp nhận rủi ro không tạo quyền license

Cần phân biệt ba tình huống:

- **Điều kiện kỹ thuật chưa thực hiện:** ví dụ thiếu notice trong gói; phải thực hiện hoặc có kết luận hợp lệ khác về cách đáp ứng.
- **Thiếu quyền/điều kiện sử dụng chưa rõ:** cần làm rõ, có thỏa thuận phù hợp, đổi cách dùng hoặc thay component.
- **Rủi ro security còn lại:** có thể có quy trình chấp nhận rủi ro theo policy và đúng thẩm quyền.

Không dùng ngoại lệ bảo mật để cho qua việc chưa chứng minh quyền phân phối. Không gọi mọi điều kiện license là “rủi ro có thể tự waive”.

Ngược lại, việc đã có hợp đồng cấp quyền không giải quyết một đường tải code không kiểm soát hoặc quyền đọc secret quá rộng.

### 9.3. Ngoại lệ phải có phạm vi thực thi

Một ngoại lệ security được phép có thể cần:

- Subject/component và phạm vi version/digest rõ ràng.
- Sản phẩm, môi trường và cách dùng.
- Rủi ro, bằng chứng, kiểm soát bù và phần còn lại.
- Người có thẩm quyền cùng thời điểm quyết định.
- Hạn hết hiệu lực, kế hoạch xử lý và owner.
- Điều kiện làm mất hiệu lực trước hạn.
- Bằng chứng gate và vận hành thực sự giới hạn đúng phạm vi.

Gia hạn là một quyết định mới cần kiểm tra lại. Đổi version hoặc mở thêm egress không tự nằm trong ngoại lệ cũ.

Một phân tích false positive có căn cứ không phải ngoại lệ chấp nhận lỗ hổng. Phải giữ sự khác nhau này để thống kê và tái đánh giá đúng.

## 10. Độ mới, kích hoạt review lại và phục hồi

### 10.1. Tái đánh giá theo thay đổi có liên quan

| Thay đổi | Phần cần đánh giá lại |
|---|---|
| Đổi version, digest hoặc nguồn phân phối | Định danh, evidence license/security và liên kết quyết định |
| Thêm dependency bắc cầu hoặc code vendored | Phạm vi inventory, quyền sử dụng và rủi ro mới |
| Từ nội bộ sang gói khách hàng/SDK | Quyền phân phối, nghĩa vụ và evidence của gói cuối |
| Sửa, shading hoặc kết hợp component theo cách khác | Cách áp dụng điều khoản và rủi ro tích hợp |
| Mở thêm dữ liệu, đặc quyền hoặc network | Threat model, kiểm soát và kết luận ảnh hưởng |
| Có advisory, sự kiện xâm nhập hoặc thông tin nguồn mới | Security decision và hành động xử lý |
| Đổi license evidence, thỏa thuận hoặc policy | Kết luận áp dụng và phạm vi quyền |
| Kiểm soát bù mất hiệu lực hoặc ngoại lệ hết hạn | Quyền phát hành/triển khai và phương án ứng phó |

Không tự thay license lịch sử của một release chỉ vì website upstream đổi nội dung. Giữ bằng chứng đã dùng và đánh giá thông tin mới đúng phạm vi.

Với dữ liệu lỗ hổng, có thể cần cập nhật đánh giá cho artifact không đổi. Với kết luận về quyền và nghĩa vụ, có thể giữ phần còn áp dụng nhưng phải xét sự thay đổi của cách dùng hoặc bằng chứng.

### 10.2. Ví dụ các mục tiêu đo được

Dự án minh họa có thể chọn:

- Mọi release khách hàng thuộc phạm vi phải có gate cho đúng digest trước phân phối.
- Snapshot dữ liệu advisory dùng tại gate không quá 24 giờ tính từ lần đồng bộ thành công của nguồn bắt buộc; thời điểm chạy scanner không thay mốc này.
- Cảnh báo thuộc lớp khẩn cấp được policy định nghĩa phải được phân loại ban đầu trong 4 giờ từ khi hệ thống tiếp nhận hợp lệ.
- Ngoại lệ security tạm thời không vượt 14 ngày nếu chưa có quyết định gia hạn mới.
- Mọi điều kiện đến hạn trước phát hành đều có evidence phù hợp; điều kiện tiếp diễn có owner và cơ chế theo dõi.
- Khi review bị thu hồi, có thể truy xuất danh sách release/deployment liên quan theo quy mô và thời gian đáp ứng đã kiểm thử.

Những con số này là lựa chọn vận hành, không phải nghĩa vụ từ các license được nêu. Cần xác định giờ liên tục hay giờ làm việc, điểm bắt đầu và cách xử lý quá hạn.

Tỷ lệ bao phủ phải nêu mẫu số. Không loại dependency chưa phân tích được khỏi tổng số component trong scope để báo review đã hoàn tất 100%.

### 10.3. Khi dịch vụ review hoặc nguồn dữ liệu lỗi

Có thể tiếp tục dùng một kết luận đã được xác thực nếu còn đúng scope, còn hiệu lực và đáp ứng policy về độ mới. Không tự cho phép chỉ vì hệ thống cần phát hành gấp.

Nếu không chứng minh được điều kiện bắt buộc, ứng viên mới giữ trạng thái chờ hoặc bị từ chối theo nguyên nhân. Điều đó không tự yêu cầu dừng mọi workload đang chạy; xử lý vận hành cần dựa vào rủi ro thực tế và kế hoạch riêng.

Khi khôi phục kho hồ sơ, phải lấy lại quyết định, revision, evidence, ngoại lệ, nghĩa vụ và liên kết subject. Chỉ khôi phục một cột approved không đủ tái dựng quyền và điều kiện đã được áp dụng.

Rollback cũng phải xét kết luận hiện hành. Bản cũ có thể có finding mới hoặc không còn đáp ứng cách phân phối hiện tại.

## 11. Kế hoạch kiểm thử có thể giao cho đội thực hiện

Bộ dữ liệu đối chứng nên có component trực tiếp/bắc cầu, license expression khác nhau, metadata mâu thuẫn, nghĩa vụ chưa hoàn tất và rủi ro phụ thuộc cấu hình.

| Ca | Thiết lập hoặc tác động | Kết quả chấp nhận |
|---|---|---|
| T01 | Cả hai chiều đã được chấp nhận, điều kiện đến hạn hoàn tất và subject khớp | Release qua gate; quyết định gắn đúng artifact và usage profile |
| T02 | License đạt nhưng security thiếu phân tích bắt buộc | Không phát hành; lý do phản ánh thiếu dữ liệu security |
| T03 | Security đạt nhưng quyền phân phối chưa làm rõ | Không phát hành; không lấy kết quả scanner thay kết luận license |
| T04 | Component bắc cầu chưa có hồ sơ | Không báo toàn bộ đạt; xử lý khoảng trống theo policy |
| T05 | Registry ghi một license, nội dung gói có bằng chứng khác | Giữ nguồn mâu thuẫn và yêu cầu xác nhận phù hợp |
| T06 | Expression AND có một nhánh không được chấp nhận | Không rút thành nhánh thuận lợi rồi tự duyệt |
| T07 | Expression OR có quyền lựa chọn đã xác nhận | Ghi nhánh được chọn cùng evidence; vẫn giữ expression gốc |
| T08 | Scanner thấy hai license rời nhưng chưa rõ quan hệ | Không tự suy ra OR |
| T09 | LicenseRef không có text hoặc reference không phân giải được | Chưa đủ evidence, không tự approve |
| T10 | Notice có trong repository nhưng không nằm ở nơi được chấp nhận trong gói cuối | Không phân phối gói đó |
| T11 | Nghĩa vụ đóng gói đã hoàn tất nhưng control cô lập parser bị tắt ở production | Không coi security điều kiện đã đạt cho deployment đó |
| T12 | Scanner lỗi hoặc trả báo cáo của execution cũ | Không xuất thành “0 finding”; kiểm tra execution/subject/độ mới |
| T13 | Kết luận không bị ảnh hưởng dựa cấu hình cũ, sau đó bật chức năng liên quan | Kích hoạt đánh giá lại, không tự kế thừa kết luận cũ |
| T14 | Approval nội bộ được dùng cho bản phân phối khách hàng | Không tự cho qua; đánh giá scope và nghĩa vụ mới |
| T15 | Cùng version nhưng artifact digest đổi | Không dùng approval cũ vô điều kiện; kiểm tra phần bị ảnh hưởng |
| T16 | Người chỉ có quyền security sửa trạng thái license | Từ chối, không thay lịch sử và có audit |
| T17 | Ngoại lệ hết hạn, sai environment hoặc sai digest | Không áp dụng; gia hạn phải là quyết định mới |
| T18 | Thêm nghĩa vụ làm gói có digest mới | Kiểm tra lại gói cuối và ràng buộc evidence đúng subject |
| T19 | Thu hồi một review đang được dùng bởi nhiều release/deployment | Truy ra đủ đối tượng trong dữ liệu đối chứng, owner và khoảng trống |
| T20 | Khôi phục kho sau sự cố và thử rollback artifact cũ | Giữ revision/evidence; rollback được xét bằng policy hiện hành |

Kiểm tra schema và expression phù hợp với kiểm thử đơn vị. Liên kết inventory, quyền duyệt, scanner và gate cần kiểm thử tích hợp. Đóng gói, runtime control, rollback và phục hồi cần môi trường đại diện.

### 11.1. Ví dụ Given–When–Then

```gherkin
Given một SDK đã được chấp nhận về license có điều kiện
And điều kiện yêu cầu notice trong gói trước phân phối khách hàng
And security review và các control bắt buộc đều còn hợp lệ
When pipeline đóng gói artifact A nhưng bỏ notice bắt buộc
Then gate từ chối phân phối A với mã LICENSE_OBLIGATION_PENDING
And không đổi license decision thành REJECTED chỉ vì lỗi đóng gói
And không dùng security approval để bỏ điều kiện license
And audit gắn kết quả với digest A và nghĩa vụ chưa hoàn tất
```

Ca dương là gói đã sửa đúng điều kiện, có subject mới được xác nhận và các phần review còn áp dụng. Chỉ kiểm tra hệ thống chặn mọi thứ sẽ không chứng minh luồng phát hành hợp lệ hoạt động.

## 12. Bài tập: thiết kế review cho một SDK xuất báo cáo

Một nhóm muốn đưa SDK vào gói phần mềm giao khách hàng. SDK có các thông tin:

- Metadata công bố hai tên license nhưng chưa rõ là lựa chọn hay áp dụng cho các phần khác nhau.
- Có một parser bắc cầu nhận tài liệu từ người dùng.
- Scanner không báo CVE nhưng lần đồng bộ dữ liệu gần nhất đã quá hạn policy.
- Package chứa file notice không được cấu hình đóng gói hiện tại đưa vào bản giao.
- Bản thử nội bộ trước đây đã được duyệt.
- SDK có tùy chọn gửi telemetry ra endpoint bên ngoài.

Hãy viết đặc tả gồm:

1. Hồ sơ định danh và evidence cho SDK, parser cùng gói phát hành.
2. Cách xử lý license chưa rõ quan hệ và ai có quyền kết luận.
3. Cách xác định nghĩa vụ, thời điểm thực hiện và evidence ở gói cuối.
4. Security review cho dữ liệu tài liệu, quyền parser, telemetry và nguồn advisory.
5. Điều kiện tái sử dụng phần approval nội bộ còn áp dụng.
6. Gate, ngoại lệ được phép, audit và các ca kiểm thử âm/dương.

Một hướng giải quyết là giữ trạng thái license cần làm rõ cho đến khi có bằng chứng về quan hệ; cập nhật dữ liệu security theo policy; đánh giá parser và egress; thực hiện nghĩa vụ theo kết luận; kiểm tra gói cuối rồi mới cấp quyền phân phối đúng subject.

Chuỗi truy vết mẫu:

| Mắt xích | Nội dung |
|---|---|
| Rủi ro | R-LSR-02 và R-LSR-06: nghĩa vụ bị mất khi chuyển từ thử nội bộ sang phân phối |
| Yêu cầu | LSR-01, LSR-06 và LSR-11 |
| Kiến trúc | Kho quyết định, hệ thống quản lý nghĩa vụ, bước đóng gói và gate phát hành |
| Bằng chứng | License evidence, usage profile, notice trong gói cuối và subject digest |
| Kiểm thử | T10, T14 và T18 |
| Theo dõi vận hành | Release liên quan, owner và điều kiện tiếp diễn còn hiệu lực |

Sản phẩm cần đạt là một hợp đồng ra quyết định có thể kiểm chứng: tổ chức có quyền gì, phải thực hiện điều kiện nào, chấp nhận rủi ro security nào và làm sao chứng minh những kết luận đó đúng với phần mềm thực sự được phát hành.
