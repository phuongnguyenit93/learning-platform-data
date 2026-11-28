# Software Bill of Materials — Đặc tả yêu cầu SBOM có thể kiểm chứng

## 1. SBOM là gì và giải quyết vấn đề nào?

**Software Bill of Materials (SBOM)** là bản kê có cấu trúc về các thành phần phần mềm trong một phạm vi được xác định, cùng dữ liệu nhận diện và quan hệ giữa chúng. SBOM giúp trả lời: sản phẩm có những thành phần nào, phiên bản nào, chúng xuất hiện ở đâu và liên quan với nhau ra sao?

Khi có thông tin một thư viện có lỗ hổng, tổ chức cần tìm đúng sản phẩm, bản phát hành và môi trường có chứa thư viện đó. Nếu chỉ hỏi đội phát triển “có dùng thư viện này không?”, câu trả lời có thể bỏ sót dependency bắc cầu, thành phần được đóng gói lại hoặc một image đang chạy khác với source hiện tại.

Trong chương **Dependency và supply chain**, thuộc module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, SBOM được xem là một loại bằng chứng phục vụ yêu cầu bảo mật. Mục tiêu là chuyển phát biểu “mọi sản phẩm phải có SBOM” thành hợp đồng cụ thể về phạm vi, tính đầy đủ trong phạm vi, ràng buộc với artifact, tính xác thực, kiểm thử và cách vận hành khi thông tin chưa đủ.

Sau bài học, người học cần biết:

- Chọn đối tượng và ranh giới mà SBOM mô tả.
- Đặc tả dữ liệu nhận diện, quan hệ dependency và các trường chưa xác định.
- Ràng buộc SBOM với đúng artifact thay vì chỉ với tên sản phẩm hoặc Git commit.
- Tách việc kiểm tra SBOM khỏi quét lỗ hổng, đánh giá khả năng ảnh hưởng và phê duyệt phát hành.
- Thiết kế tiêu chí nghiệm thu, lưu trữ, kiểm soát truy cập và quy trình cập nhật bằng chứng.

Các ID thành phần, advisory, ngưỡng và schema trong bài là ví dụ học tập. Chúng không mô tả một lỗ hổng thật hay quy định bắt buộc cho mọi tổ chức.

## 2. SBOM chứng minh điều gì và còn thiếu điều gì?

Một SBOM đúng giúp truy vết thành phần trong đối tượng đã xác định. Độ tin cậy của nó còn phụ thuộc phương pháp tạo, phạm vi quan sát, nguồn dữ liệu và kiểm chứng với phần mềm thực tế.

| Bằng chứng/khái niệm | Câu hỏi chính | Không tự chứng minh |
| --- | --- | --- |
| SBOM | Đối tượng chứa hoặc phụ thuộc vào thành phần nào? | Mọi thành phần đều an toàn, được khai báo đủ hoặc đang được thực thi |
| Manifest/lockfile | Công cụ build khai báo hoặc resolve dependency nào? | Artifact cuối chỉ chứa đúng các dependency đó |
| SBOM từ artifact | Công cụ nhận diện được gì trong đối tượng đã phân tích? | Công cụ thấy được mọi thành phần bị biến đổi, liên kết tĩnh hoặc tải động |
| Báo cáo quét lỗ hổng | Thành phần khớp dữ liệu lỗ hổng nào tại lần quét? | Không còn lỗ hổng chưa biết, hoặc mọi kết quả đều khai thác được |
| Build provenance | Artifact được tạo bởi quy trình và đầu vào nào theo bằng chứng? | Bản kê thành phần chắc chắn đầy đủ hoặc mã không có hành vi độc hại |
| Chữ ký/chứng thực SBOM | Dữ liệu được ràng buộc với danh tính ký theo cơ chế được kiểm tra | Người ký được tổ chức tin cậy, hoặc mọi khẳng định trong tài liệu đều đúng |
| VEX/đánh giá khả năng ảnh hưởng | Trong phạm vi được nêu, lỗ hổng được đánh giá ảnh hưởng thế nào? | Mọi phiên bản, cấu hình hoặc artifact khác đều không bị ảnh hưởng |
| Danh mục phần mềm triển khai | Instance/môi trường đang chạy artifact và thành phần nào? | SBOM của một bản build cũ mô tả chính xác trạng thái runtime hiện tại |

VEX trong bài là thông tin đánh giá khả năng ảnh hưởng của lỗ hổng, được quản lý như bằng chứng riêng có phạm vi, nguồn và điều kiện hiệu lực. Không dùng một trạng thái “không bị ảnh hưởng” thiếu căn cứ để xóa dấu vết dependency khỏi SBOM.

Dữ liệu license có thể hỗ trợ quy trình quản lý nghĩa vụ sử dụng phần mềm. Có tên license trong SBOM không tự kết luận sản phẩm đã đáp ứng mọi nghĩa vụ; cần quy trình đánh giá tương ứng và nguồn dữ liệu rõ ràng.

## 3. Chọn đối tượng, phạm vi và thời điểm tạo

### 3.1. Đối tượng được mô tả

Đối tượng, hay **subject**, có thể là một archive ứng dụng, một package, một executable, một container image hoặc một tập sản phẩm có liên kết tới các artifact con. Cần định danh chính xác đối tượng mà SBOM áp dụng.

Một tag như `production` hoặc `latest` có thể đổi đích; tên file `app.jar` cũng có thể được tái sử dụng. Chúng là nhãn thuận tiện, không đủ làm ràng buộc bất biến giữa SBOM và phần mềm. Cần thêm digest của đúng đối tượng theo cơ chế phát hành đã chọn.

Với image nhiều nền tảng, phải phân biệt digest của image index/manifest tổng với digest của image cho từng nền tảng. Một SBOM chỉ phân tích một nền tảng không mặc nhiên mô tả các nền tảng còn lại. Tương tự, hash một file export không tự đồng nghĩa với digest định danh image trong registry.

### 3.2. Các phạm vi thường gặp

| Phạm vi | Nội dung cần quan tâm | Ràng buộc cần ghi |
| --- | --- | --- |
| Source/dependency declaration | Dependency khai báo, file được vendoring, module dự án | Commit, cấu hình/profile và những gì chưa thể suy ra từ source |
| Build/resolution | Graph đã resolve, plugin, generator, toolchain theo phạm vi | Build ID, đầu vào, môi trường và thành phần chỉ dùng khi build |
| Artifact ứng dụng | Thư viện đóng gói, mã bị shade/repackage, binary/native kèm theo | Digest của artifact cuối và giới hạn phương pháp nhận diện |
| Container/thiết bị/phân phối | Ứng dụng, runtime và package hệ điều hành trong đối tượng | Platform, image/package digest và liên kết SBOM con nếu dùng |
| Runtime/deployment | Plugin tải động, volume hoặc package được cài thêm, runtime ngoài artifact | Snapshot triển khai, thời điểm quan sát và cơ chế phát hiện thay đổi |

Không trộn thành phần chỉ chạy ở build với thành phần shipped/runtime mà không ghi loại quan hệ hoặc phạm vi. Một plugin build bị lộ vẫn là rủi ro supply chain, nhưng không nên được mô tả sai như một thư viện được đóng gói trong sản phẩm.

### 3.3. Hợp đồng phạm vi minh họa

Giả sử một bản phát hành gồm JAR ứng dụng chạy trong container. Chính sách có thể yêu cầu:

1. SBOM của JAR bao phủ các thành phần được đóng gói, bao gồm dependency bắc cầu và thư viện native đi kèm trong phạm vi có thể kiểm kê.
2. SBOM của image hoặc các SBOM liên kết bao phủ runtime và package hệ điều hành thực sự có trong từng image được phát hành.
3. Bản kê build riêng hoặc loại quan hệ riêng cho plugin/toolchain thuộc phạm vi cần theo dõi.
4. Runtime không được tự cài thêm dependency ngoài hợp đồng; nếu cho phép, cần inventory cập nhật và đánh giá bổ sung trước sử dụng theo chính sách.
5. Thành phần chưa nhận diện được phải được nêu như phần thiếu bằng chứng, có owner và cách xử lý.

“Đầy đủ” ở đây nghĩa là đáp ứng phạm vi đã công bố bằng các phép đối chiếu được xác định. Không khẳng định một scanner chứng minh không còn bất kỳ thành phần ẩn nào trong mọi loại phần mềm.

## 4. Mô hình đe dọa và các bất biến

### 4.1. Tài sản và tác nhân

Tài sản cần bảo vệ là tính đúng đắn của quyết định phát hành, khả năng tìm bản triển khai bị ảnh hưởng, tính toàn vẹn của bằng chứng thành phần và dữ liệu supply chain nhạy cảm.

Giả định tác nhân có thể thay tài liệu được gửi lên cổng tiếp nhận, cung cấp SBOM của bản khác, bỏ thành phần khỏi bản kê hoặc tác động một bước build có quyền thấp hơn nguồn chính sách phê duyệt. Một nhà cung cấp cũng có thể gửi SBOM chưa đầy đủ mà không có chủ đích xấu.

Nếu cả artifact, pipeline đo đạc và mọi danh tính/phê duyệt tin cậy đều bị chiếm, một SBOM tự khai không khôi phục được niềm tin. Cần kiểm soát pipeline, nguồn artifact và quy trình phục hồi ngoài bản kê.

| Risk ID | Kịch bản | Hậu quả | Hướng yêu cầu |
| --- | --- | --- | --- |
| SBR-01 | SBOM thuộc artifact khác hoặc tag đã đổi | Tìm sai phiên bản, bỏ sót rủi ro của bản đang chạy | Ràng buộc subject bằng digest và đối chiếu khi promote/deploy |
| SBR-02 | Chỉ liệt kê dependency trực tiếp | Bỏ sót thư viện bắc cầu có liên quan | Đối chiếu graph resolve với nội dung artifact theo phạm vi |
| SBR-03 | Shade, copy thủ công hoặc binary native không được nhận diện | Có thành phần trong sản phẩm nhưng inventory không biết | Dùng nguồn đối chiếu bổ sung, công bố blind spot/unknown |
| SBR-04 | Đổi SBOM và hash công bố từ cùng nguồn bị chiếm | Bản kê giả vẫn vượt kiểm tra hash đơn thuần | Xác thực nguồn/chứng thực và tách gốc tin cậy |
| SBR-05 | Tên giống nhau, version hoặc ecosystem sai | Gán nhầm lỗ hổng hoặc bỏ qua thành phần đúng | Định danh có namespace/ecosystem và xử lý match chưa chắc chắn |
| SBR-06 | Tài liệu hợp lệ schema nhưng thiếu quan hệ hoặc tham chiếu sai | Không biết thành phần thuộc subject nào hoặc đường dependency nào | Kiểm tra graph, ID duy nhất và tham chiếu tồn tại |
| SBR-07 | Dữ liệu lỗ hổng cũ hoặc scanner lỗi nhưng báo sạch | Phê duyệt dựa trên dữ liệu không đủ | Phân biệt không tìm thấy, không quét được và dữ liệu quá tuổi |
| SBR-08 | Dùng VEX/ngoại lệ ngoài artifact hoặc điều kiện áp dụng | Bỏ chặn một bản thực sự cần xử lý | Ràng buộc assessment với phạm vi và kiểm tra lại hiệu lực |
| SBR-09 | Upload tài liệu quá lớn hoặc chứa tham chiếu từ xa | Quá tải parser hoặc tải tài nguyên ngoài ý muốn | Giới hạn đầu vào, parse an toàn và tắt resolve ngoài hợp đồng |
| SBR-10 | Runtime cài thêm plugin sau khi tạo SBOM | SBOM phát hành khác phần mềm thực thi | Kiểm soát nạp động và theo dõi inventory triển khai |
| SBR-11 | Phát tán SBOM chứa secret, đường dẫn nội bộ hoặc thông tin nhạy cảm | Lộ dữ liệu và cấu trúc hệ thống | Tối thiểu hóa, phân quyền, phiên bản chia sẻ có kiểm soát |
| SBR-12 | Rollback chỉ khôi phục artifact, mất liên kết bằng chứng | Không truy vết được thành phần/quyết định ở bản phục hồi | Lưu và phục hồi bộ artifact–SBOM–policy–assessment có liên kết |

### 4.2. Bất biến cần bảo vệ

- Quyết định cho một artifact chỉ dùng SBOM có subject khớp chính artifact đó và phạm vi đủ cho quyết định.
- Tài liệu chưa xác thực, graph sai hoặc phần thiếu bằng chứng không được tự biến thành “không có rủi ro”.
- Một dependency không biến mất khỏi inventory chỉ vì đã được miễn trừ hoặc đánh giá không ảnh hưởng trong một tình huống.
- Không cho sửa SBOM sau khi kiểm tra/chứng thực mà vẫn sử dụng kết quả xác minh cũ.
- Quyết định ở build không tự áp dụng mãi cho mọi triển khai, cấu hình và thông tin lỗ hổng về sau.

## 5. Hợp đồng dữ liệu của SBOM

### 5.1. Các nhóm dữ liệu cần xác định

| Nhóm | Nội dung ví dụ | Điều cần kiểm chứng |
| --- | --- | --- |
| Tài liệu | Document ID, schema/phiên bản, thời điểm tạo, công cụ/author | Định dạng được hỗ trợ, nguồn dữ liệu, không nhập nhằng phiên bản |
| Subject | Loại artifact, tên, version, digest, platform khi cần | Khớp đối tượng cuối cùng và thuật toán/dạng digest đã công bố |
| Thành phần | Component reference, name, version, ecosystem/namespace, supplier khi biết | Nhận diện đúng, không dùng chuỗi version tùy ý để đoán |
| Định danh bổ sung | Package URL hoặc định danh phù hợp ecosystem, digest thành phần khi có | Không tự sinh định danh sai khi không có đủ bằng chứng |
| Quan hệ | Subject chứa/phụ thuộc thành phần nào; các cạnh bắc cầu | ID duy nhất, tham chiếu tồn tại, loại quan hệ và phạm vi có nghĩa |
| Phạm vi và giới hạn | Included/excluded, thành phần chưa nhận diện, nguồn đối chiếu | Không im lặng loại bỏ phần công cụ không nhìn thấy |
| Metadata khác | Nguồn, license khai báo, tham chiếu tài liệu, thông tin chứng thực | Nêu mức độ chắc chắn và bảo vệ dữ liệu nhạy cảm |

Đây là nhóm yêu cầu dữ liệu của ví dụ, không phải tuyên bố mọi định dạng đều bắt buộc cùng tên field. Có thể chọn định dạng trao đổi như SPDX hoặc CycloneDX, nhưng cần chốt phiên bản schema, profile, trường bắt buộc và cách xử lý trường không được hỗ trợ. Đổi định dạng không được làm mất quan hệ hoặc phần unknown mà không được phát hiện.

### 5.2. Định danh và phần chưa biết

Tên hiển thị đơn lẻ thường chưa đủ: hai ecosystem hoặc hai nhà cung cấp có thể có thành phần cùng tên. Version, namespace, ecosystem, variant và bằng chứng artifact giúp tránh gán nhầm.

Package URL có thể hỗ trợ nhận diện package, nhưng không thay digest của bản build cụ thể; hai artifact khác bytes vẫn có thể dùng cùng tên/version nếu quy trình xuất bản cho phép thay nội dung. Không suy rằng package có cùng tên là đúng package chỉ để tăng tỷ lệ match lỗ hổng.

Nếu không biết version hoặc supplier, phải ghi trạng thái chưa xác định theo profile và lưu nguồn/owner cần xác minh. Không thay unknown bằng `0.0.0`, chuỗi rỗng hoặc “latest” để qua kiểm tra. Một lỗi kiểm kê không được mặc định thành không có thành phần.

### 5.3. Quan hệ và tính đầy đủ trong phạm vi

Mỗi component reference phải duy nhất trong tài liệu. Mỗi cạnh phải trỏ tới reference có tồn tại hoặc một đối tượng ngoài được tham chiếu đúng hợp đồng. Không âm thầm bỏ cạnh lỗi rồi coi graph hợp lệ.

Không bắt mọi graph dependency phải là cây. Một thành phần có thể được nhiều thành phần khác dùng chung; quan hệ vòng cũng cần được xử lý theo loại dữ liệu thay vì làm parser lặp vô hạn. Thuật toán duyệt cần tập visited và giới hạn tài nguyên.

Đối chiếu graph với dependency resolution giúp phát hiện phần bỏ sót trong khai báo. Đối chiếu nội dung artifact giúp phát hiện khác biệt do đóng gói. Hai nguồn có thể cùng không nhìn thấy một thư viện đã bị biến đổi; cần nêu giới hạn nhận diện và bằng chứng bổ sung khi rủi ro yêu cầu.

## 6. Bộ yêu cầu SBOM có thể kiểm chứng

Bảng sau là chính sách minh họa cho một nhóm sản phẩm. Owner cụ thể và các ngưỡng phải được chốt theo rủi ro, khả năng công cụ và vòng đời hỗ trợ; không trình bày chúng như nghĩa vụ mặc định của một tiêu chuẩn.

| ID | Yêu cầu | Owner | Bằng chứng đạt |
| --- | --- | --- | --- |
| SBOM-01 | Mỗi loại artifact phát hành phải có phạm vi SBOM, phương pháp tạo/đối chiếu, phần loại trừ và owner được phê duyệt. | Chủ sản phẩm/build | Hồ sơ phạm vi chỉ rõ application, OS/runtime, platform và thành phần build/runtime thuộc trách nhiệm nào |
| SBOM-02 | Chỉ nhận schema/phiên bản/profile được hỗ trợ; kiểm tra trường bắt buộc và ngữ nghĩa cần cho quyết định. Không coi parse được JSON/XML là đã hợp lệ SBOM. | Nền tảng supply chain | Tài liệu đúng được nhận; sai schema, profile thiếu trường hoặc trường không hỗ trợ quan trọng bị xử lý rõ |
| SBOM-03 | Subject phải gắn với digest của đúng artifact cuối theo loại đối tượng; mỗi platform/đối tượng con phải có bằng chứng tương ứng theo phạm vi. | Build/release | Thay một byte hoặc chuyển sang image/platform khác làm ràng buộc không đạt; tag không thay digest làm định danh kiểm chứng |
| SBOM-04 | Nguồn SBOM/chứng thực phải được xác minh với danh tính, quyền và gốc tin cậy được phép; kết quả phải ràng buộc đúng bytes tài liệu và subject. | Bảo mật/nền tảng | Sửa tài liệu, dùng signer không được duyệt hoặc tái dùng bằng chứng của subject khác không được chấp nhận |
| SBOM-05 | Thành phần phải có reference duy nhất và dữ liệu nhận diện theo profile; phần chưa biết phải biểu diễn rõ, không tự bịa version hoặc supplier. | Build/nhà cung cấp | Kiểm tra trùng ID, ecosystem/version sai và unknown; có owner xử lý phần thiếu |
| SBOM-06 | Quan hệ cần cho phạm vi phải được giữ, tham chiếu phải giải được theo hợp đồng; duyệt graph không mất thành phần dùng chung hoặc lặp vô hạn. | Nền tảng | Test cạnh thiếu đích, thành phần bắc cầu, shared dependency và graph có vòng theo loại quan hệ |
| SBOM-07 | Đối chiếu SBOM với graph resolve và nội dung artifact trong phạm vi đã duyệt; mọi khác biệt phải có quyết định, không âm thầm bỏ qua blind spot. | Build/chủ sản phẩm | Fixture có thư viện copy/shade/native hoặc package ngoài manifest làm phát hiện chênh lệch/unknown |
| SBOM-08 | Mỗi artifact mới phải tạo hoặc cung cấp SBOM áp dụng đúng nó trước phát hành; bước tạo lỗi không được trả lại SBOM cũ như bằng chứng mới. | Build/release | Build mới có subject digest mới; lỗi generator chặn hoặc đi đúng ngoại lệ, không lấy output lần trước |
| SBOM-09 | Báo cáo đánh giá lỗ hổng phải ghi engine/ruleset, nguồn và thời điểm dữ liệu, thời điểm đánh giá; ví dụ dữ liệu không quá 24 giờ tại gate. Scan lỗi/quá tuổi không được báo như không tìm thấy lỗ hổng. | Quản lý lỗ hổng | Tiêm database cũ, timeout và engine lỗi; quyết định phân biệt đủ dữ liệu với chưa đánh giá được |
| SBOM-10 | VEX/ngoại lệ chỉ áp dụng đúng advisory, thành phần, artifact/phạm vi và điều kiện được phê duyệt; hết hiệu lực hoặc thay điều kiện phải đánh giá lại. | Chủ sản phẩm/bảo mật | Thử dùng assessment cho digest/cấu hình khác, thiếu căn cứ hoặc đã hết hạn; không tự được miễn trừ |
| SBOM-11 | Gate phải phân biệt thiếu SBOM, subject mismatch, xác thực sai, coverage gap, finding và assessment chưa rõ. Hành vi chặn/ngoại lệ được đặc tả trước, không fail open khi công cụ lỗi. | Release/bảo mật | Test từng trạng thái và audit lý do; có test dương tính để chứng minh artifact đủ điều kiện vẫn đi qua |
| SBOM-12 | Deployment phải liên kết tới artifact digest và SBOM tương ứng; cài thêm/thay thành phần ở runtime phải bị chặn hoặc cập nhật inventory, đánh giá trước sử dụng theo policy. | Vận hành/nền tảng | Thay image hoặc nạp plugin ngoài hợp đồng tạo drift và không dùng nhầm kết luận của inventory cũ |
| SBOM-13 | Cổng nhận phải giới hạn tài nguyên: ví dụ tối đa 10 MiB dữ liệu sau giải nén, 100.000 component, 500.000 quan hệ và 30 giây parse/validate trong worker có giới hạn tài nguyên. Không tự tải external reference. | Nền tảng | Payload nén phình lớn, graph quá giới hạn hoặc reference từ xa không gây tải ngoài ý muốn/quá tải không kiểm soát |
| SBOM-14 | SBOM phải được phân loại và phân quyền; không chứa secret. Bản chia sẻ ra ngoài phải qua quy tắc giảm thiểu và có định danh/bằng chứng riêng nếu nội dung đổi. | Chủ dữ liệu/bảo mật | Kiểm tra secret/metadata nhạy cảm, truy cập trái quyền và bản đã biên tập không dùng chữ ký của bản gốc |
| SBOM-15 | Lưu liên kết artifact–SBOM–chứng thực–policy–assessment trong suốt thời gian hỗ trợ và ví dụ thêm 180 ngày, theo quy tắc lưu giữ/điều tra hiện hành; kiểm tra khả năng khôi phục. | Release/vận hành | Truy vấn được bản cũ và phục hồi liên kết/bằng chứng; không xóa dữ liệu đang thuộc yêu cầu lưu giữ hợp lệ |
| SBOM-16 | Có quy trình truy vấn thành phần/advisory tới sản phẩm và deployment; ví dụ lập danh sách ban đầu trong 4 giờ kể từ tiếp nhận advisory cần xử lý, nêu cả match chưa chắc chắn. | Ứng phó/chủ sản phẩm | Diễn tập tìm đúng artifact, platform, môi trường và owner; không loại unknown chỉ để đủ thời hạn |
| SBOM-17 | Promote, rollback và restore phải kiểm tra subject, phạm vi và policy hiện hành; SBOM đúng của bản cũ không tự làm quyết định rủi ro cũ còn hiệu lực. | Release/vận hành | Restore bản trước với assessment cũ hoặc quyền signer đã thay; quyết định dựa trên quy tắc hiện hành |
| SBOM-18 | Audit phải ghi artifact/SBOM digest, revision policy, danh tính nguồn và reason code; metric phải quan sát coverage/unknown/đánh giá lỗi mà không công bố secret hoặc tạo nhãn vô hạn. | Nền tảng/vận hành | Đối chiếu lại được quyết định gate; log lỗi không dump nội dung nhạy cảm hoặc gọi “clean” khi thiếu bằng chứng |

### 6.1. Mẫu đặc tả cho ràng buộc subject

```text
ID: SBOM-03
Mục tiêu: quyết định phát hành chỉ áp dụng cho đúng artifact đã được kiểm kê
Rủi ro: SBR-01
Phạm vi: JAR cuối sau đóng gói và image của từng platform được phát hành
Đầu vào: artifact bất biến, subject digest trong tài liệu/bằng chứng được xác thực
Điều kiện đạt:
  - Kiểu đối tượng và thuật toán/dạng digest được hỗ trợ
  - Digest đo trên đúng đối tượng khớp digest subject được xác thực
  - Platform và các SBOM con đáp ứng phạm vi đã phê duyệt
Không đạt:
  - Không promote/deploy theo quyết định bình thường
  - Ghi subject mismatch hoặc missing-scope evidence; không dùng tag thay digest
Owner: đội build và release
Test: T-SBOM-02, T-SBOM-03, T-SBOM-14
Bằng chứng: artifact digest, SBOM digest, platform, policy revision và quyết định
```

## 7. Kiến trúc tạo, xác thực và sử dụng SBOM

### 7.1. Luồng tham khảo

```text
Source + graph resolve + thành phần đóng gói
                 |
                 v
Build/đóng gói artifact cuối theo quy trình được kiểm soát
                 |
                 +--> Tạo/đối chiếu SBOM và ghi giới hạn nhận diện
                 |              |
                 |              v
                 |     Kiểm tra schema + graph + coverage
                 |              |
                 |              v
                 |     Chứng thực đúng tài liệu/subject theo cơ chế được duyệt
                 |              |
                 v              v
Kho artifact bất biến <--> Kho bằng chứng và chỉ mục thành phần
                 |
                 v
Đánh giá lỗ hổng + assessment/VEX/ngoại lệ có phạm vi
                 |
                 v
Gate theo policy hiện hành → promote/deploy đúng digest
                 |
                 v
Inventory runtime + truy vấn sự cố + tái đánh giá khi dữ liệu thay đổi
```

Với SBOM do nhà cung cấp gửi, hệ thống vẫn phải kiểm tra nguồn, subject, phạm vi và chất lượng theo hợp đồng. Không thể kết luận inventory đầy đủ chỉ vì tài liệu được ký bởi nhà cung cấp.

### 7.2. Thứ tự và tính bất biến

Artifact phải được xác định sau các bước có thể đổi bytes hoặc cấu trúc định danh của nó. Nếu ký/đóng gói lại artifact làm digest đổi, cần ràng buộc SBOM với đối tượng cuối hoặc có chuỗi biến đổi/bằng chứng phù hợp được hợp đồng chấp nhận.

SBOM có thể tham chiếu artifact digest, còn digest của chính SBOM được tính riêng trên tài liệu đã hoàn chỉnh. Không tự thiết kế vòng tham chiếu trong đó tài liệu hoặc artifact chứa hash của chính toàn bộ bytes đang bị sửa. Khi nhúng SBOM vào artifact, phải có quy tắc xác định subject và thứ tự đóng gói rõ ràng; không giả định hash trước khi nhúng vẫn là hash artifact cuối.

Sau khi kiểm tra/chứng thực, lưu tài liệu và artifact theo định danh bất biến. Nếu sửa một trường, kể cả metadata, phải có tài liệu/revision và bằng chứng tương ứng theo cơ chế ký. Không cho một URL có thể ghi đè âm thầm thay nội dung đã được gate chấp nhận.

### 7.3. Kiểm tra tại gate

```text
evaluate_release(artifact, sbom, evidence, policy):
    enforce_input_and_resource_limits(sbom, evidence)
    parse_with_external_resolution_disabled()
    validate_supported_schema_profile_and_semantics()
    verify_document_source_and_authorized_identity(evidence, policy)
    bind_verified_document_bytes_to_its_evidence()
    verify_subject_digest_type_platform_and_artifact_binding(artifact)
    validate_component_identifiers_and_relationships()
    reconcile_declared_scope_with_resolution_and_artifact_observations()
    classify_unknowns_and_coverage_gaps()
    assessment = evaluate_with_approved_fresh_vulnerability_data()
    apply_only_in_scope_current_vex_and_approved_exceptions(assessment)
    decide_using_explicit_policy_without_error_to_success_fallback()
    persist_audit_and_evidence_links()
```

Parse an toàn phải diễn ra với dữ liệu chưa được tin cậy; xác thực tài liệu không cho phép bỏ giới hạn đầu vào. Ngược lại, parse thành công không làm nguồn tài liệu trở thành đáng tin. Cấu hình trust của bộ kiểm chứng không được lấy tùy ý từ chính tài liệu đang cần kiểm chứng.

## 8. Ví dụ SBOM và đường dependency

Ví dụ này mô tả một JAR chứa `demo-http` và `demo-parser`. Tất cả tên/version là dữ liệu giả định. JSON sau là **mô hình nội bộ để giải thích yêu cầu**, không phải tài liệu SPDX hoặc CycloneDX có thể gửi thẳng tới validator của các định dạng đó.

```json
{
  "documentId": "sbom-demo-release-1",
  "profile": "training-application-archive-v1",
  "subject": {
    "componentRef": "app",
    "kind": "application-archive",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "scope": {
    "included": ["bundled-java-components"],
    "excluded": ["runtime-jre", "container-os", "build-plugins"],
    "unknownComponents": []
  },
  "components": [
    {
      "ref": "app",
      "name": "demo-orders",
      "version": "1.0.0"
    },
    {
      "ref": "http-client",
      "name": "demo-http",
      "version": "2.1.0",
      "packageUrl": "pkg:maven/example.demo/demo-http@2.1.0"
    },
    {
      "ref": "parser",
      "name": "demo-parser",
      "version": "3.1.0",
      "packageUrl": "pkg:maven/example.demo/demo-parser@3.1.0"
    }
  ],
  "relationships": [
    {"from": "app", "type": "dependsOn", "to": "http-client"},
    {"from": "http-client", "type": "dependsOn", "to": "parser"}
  ]
}
```

Digest gồm 64 chữ `a` chỉ là giá trị tổng hợp để minh họa hình dạng dữ liệu, không phải digest đã đo của một artifact thật. Một gate thực tế phải tự đo hoặc xác minh digest của đối tượng lấy từ luồng phát hành được kiểm soát và kiểm tra với bằng chứng đã xác thực.

Graph minh họa là `app → demo-http → demo-parser`. Nếu chỉ nhìn dependency trực tiếp của app thì có thể không thấy parser. Nếu xóa component `parser` nhưng vẫn giữ cạnh tới nó, kiểm tra tham chiếu phải không đạt. Nếu xóa cả component lẫn cạnh, graph có thể vẫn hợp lệ cấu trúc; cần đối chiếu resolution/nội dung artifact để tìm phần thiếu.

Danh sách `unknownComponents: []` là một khẳng định của tài liệu, không phải bằng chứng scanner đã nhìn thấy mọi thứ. Cần lưu phương pháp, đối chiếu và giới hạn để đánh giá khẳng định đó.

Phần `excluded` không cho phép dùng bản kê này để kết luận toàn container đã được kiểm kê. Gate cho image còn cần bằng chứng runtime/OS và platform theo phạm vi. Bản kê build riêng phải theo dõi plugin/toolchain cần thiết; không gộp chúng vào quan hệ runtime sai nghĩa chỉ để tăng số component.

### 8.1. Ví dụ đánh giá một advisory tổng hợp

Giả sử advisory thử `ADVISORY-DEMO-001` nêu phạm vi ảnh hưởng của `example.demo/demo-parser` là version từ 3.0.0 đến trước 3.2.0. Đây là điều kiện fixture, không phải thông tin về thư viện thật.

Với inventory trên, bước match phải nhận ra `demo-parser@3.1.0` là candidate và chỉ ra đường bắc cầu từ app. Sau đó áp policy theo mức độ, khả năng ảnh hưởng và bằng chứng được phép. Không bỏ candidate chỉ vì ứng dụng không khai báo parser trực tiếp.

Nếu bản tiếp theo dùng parser 3.2.1, nó không nằm trong khoảng ảnh hưởng của advisory tổng hợp này theo quy tắc version của fixture. Điều đó không chứng minh bản mới không có lỗ hổng khác. Cần SBOM của artifact mới và đánh giá lại với dữ liệu hiện hành.

Một VEX nói “không bị ảnh hưởng vì đường mã không thể đạt tới trong cấu hình X” chỉ có thể được áp trong đúng artifact/điều kiện đã được đánh giá. Đổi cấu hình, plugin hoặc cách gọi có thể làm kết luận đó mất hiệu lực; component vẫn phải tồn tại trong inventory.

## 9. Triển khai kiểm tra ràng buộc artifact

### 9.1. Ví dụ Java đo digest của archive

Ví dụ dùng JDK 17 và chỉ minh họa một phép kiểm tra của SBOM-03: so sánh SHA-256 của file archive với subject digest đã lấy từ bằng chứng được xác thực. Đường dẫn file do pipeline kiểm soát, không lấy tùy ý từ một URL/path nằm trong SBOM chưa được tin cậy.

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;

public final class SbomArtifactBinding {
    public static boolean matchesArchive(
            Path artifact, String authenticatedSubjectSha256)
            throws IOException, NoSuchAlgorithmException {
        Objects.requireNonNull(artifact);
        if (authenticatedSubjectSha256 == null
                || !authenticatedSubjectSha256.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Invalid subject digest encoding");
        }

        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];
        try (InputStream input = Files.newInputStream(artifact)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                sha256.update(buffer, 0, count);
            }
        }

        byte[] expected = HexFormat.of().parseHex(authenticatedSubjectSha256);
        byte[] actual = sha256.digest();
        return MessageDigest.isEqual(expected, actual);
    }
}
```

Không catch lỗi đọc file rồi trả true hoặc dùng lại kết quả digest của lần chạy trước. Sai dạng digest là lỗi đầu vào; không mở rộng sang thuật toán khác do tài liệu tự chọn nếu policy không cho phép.

Hàm không xác minh chữ ký SBOM, danh tính author, nội dung JAR, graph, coverage hay lỗ hổng. Nếu expected digest cũng do kẻ tấn công tùy ý thay, phép so sánh khớp chưa chứng minh nguồn artifact đáng tin. Với image, phải dùng digest đúng loại đối tượng từ luồng registry đã được kiểm soát, không dùng hash file export này để giả làm image digest.

Cần ngăn thay artifact giữa lúc đo và lúc promote/deploy. Biện pháp phù hợp là dùng đối tượng bất biến theo digest và ràng buộc việc quét, lưu bằng chứng, promote và triển khai với cùng định danh đó. Không chỉ kiểm tra một đường dẫn file có thể bị ghi đè rồi tin tên đường dẫn ở bước sau.

### 9.2. Kết quả gate phải có nghĩa rõ ràng

| Trạng thái | Ý nghĩa | Hành vi minh họa |
| --- | --- | --- |
| PASS | Bằng chứng đủ trong phạm vi và policy cho phép | Promote đúng artifact digest, lưu quyết định cùng revision |
| INVALID_DOCUMENT | Sai schema, định danh hoặc graph theo hợp đồng | Không dùng tài liệu cho quyết định; yêu cầu sửa đúng bản |
| SUBJECT_MISMATCH | SBOM không ràng buộc đúng artifact/platform | Chặn promote; không tìm SBOM “gần giống” theo tên |
| UNTRUSTED_SOURCE | Chưa xác thực được nguồn hoặc danh tính không được phép | Chặn theo policy; không coi mọi chữ ký hợp lệ là được ủy quyền |
| COVERAGE_GAP | Thiếu thành phần/phạm vi hoặc còn unknown cần xử lý | Chặn hay chuyển luồng ngoại lệ đúng điều kiện, có owner |
| ASSESSMENT_UNAVAILABLE | Scanner, dữ liệu hoặc bước đánh giá không đủ điều kiện | Không đổi thành “không có finding”; xử lý lỗi/ngoại lệ đã phê duyệt |
| FINDINGS_BLOCKED | Finding/đánh giá thuộc điều kiện cấm của policy | Khắc phục hoặc làm assessment có bằng chứng, không xóa component |
| EXCEPTION_APPROVED | Có quyết định chấp nhận rủi ro đúng phạm vi, còn hiệu lực | Ghi riêng với PASS thông thường; giữ audit, deadline và trách nhiệm |

Một policy có thể cho phép một số thiếu hụt metadata rủi ro thấp, nhưng phải nêu chính xác trường, đối tượng, thời hạn và người chịu trách nhiệm. Không dùng một cờ `ignoreErrors` chung để giải quyết mọi lỗi parser, digest và vulnerability data.

## 10. Độ mới của SBOM và độ mới của đánh giá lỗ hổng

### 10.1. Hai vòng đời khác nhau

SBOM mô tả thành phần của một đối tượng trong phạm vi xác định. Nếu artifact bất biến và phạm vi/nhận diện vẫn đúng, SBOM không tự trở thành sai chỉ vì được tạo từ tháng trước.

Thông tin lỗ hổng, quy tắc match, trạng thái hỗ trợ, cấu hình triển khai và assessment có thể thay đổi trong khi bytes artifact không đổi. Vì vậy cần tái đánh giá rủi ro mà không nhất thiết giả lập một SBOM mới để làm timestamp trông còn mới.

| Thay đổi | Hành động cần xem xét |
| --- | --- |
| Artifact/build output thay đổi | Tạo/cung cấp SBOM áp dụng đúng subject mới, xác thực và đánh giá lại |
| Công cụ nhận diện phát hiện thành phần trước đây bỏ sót | Tạo revision bằng chứng mới cho subject hiện tại, giữ lịch sử và xem lại quyết định bị ảnh hưởng |
| Dữ liệu advisory hoặc ruleset match thay đổi | Đánh giá lại inventory liên quan bằng dữ liệu đủ điều kiện |
| VEX/ngoại lệ hết hạn hoặc căn cứ thay đổi | Đánh giá lại trạng thái ảnh hưởng và quyết định policy |
| Runtime cài thêm plugin hoặc đổi thành phần qua volume | Cập nhật inventory/phạm vi và kiểm soát trước sử dụng theo hợp đồng |
| Chỉ đổi nhãn triển khai, giữ nguyên digest | Giữ liên kết đúng subject; vẫn kiểm tra policy/assessment hiện hành cho quyết định triển khai |

Mục tiêu 24 giờ ở SBOM-09 cần chỉ rõ tuổi của dữ liệu nguồn được đánh giá, không chỉ thời điểm scanner chạy. Chạy scanner lúc này trên database cũ một tuần không đáp ứng mục tiêu đó. Cũng cần phân biệt thời điểm đồng bộ dữ liệu với việc nguồn đã công bố/đính chính thông tin gì; tuổi dữ liệu ngắn không chứng minh mọi lỗ hổng đã được biết.

### 10.2. Match, tính khả dụng và quyết định

Version phải được so theo quy tắc thích hợp của ecosystem hoặc advisory, không so chuỗi từ điển một cách tùy tiện. Một định danh có supplier/ecosystem khác không được match chỉ vì tên hiển thị giống nhau. Match chưa chắc chắn cần được phân loại để điều tra thay vì âm thầm bỏ hoặc tự kết luận chắc chắn bị ảnh hưởng.

Một finding có thể cần được ưu tiên theo điều kiện khai thác, mức phơi lộ và tác dụng nghiệp vụ. SBOM hỗ trợ tìm đối tượng; nó không thay threat model hay kiểm chứng khả năng ảnh hưởng của ứng dụng.

VEX/assessment cần nêu nguồn có quyền, advisory/phiên bản dữ liệu liên quan, component/subject, điều kiện triển khai, lý do, bằng chứng và trigger đánh giá lại. Không lấy câu “không dùng chức năng này” làm kết luận không ảnh hưởng nếu chưa chứng minh điều kiện đó trong phạm vi được chấp nhận.

## 11. Lưu trữ, chia sẻ, vận hành và ứng phó

### 11.1. Bộ bằng chứng có liên kết

Nên lưu riêng nhưng liên kết được:

- Artifact digest và metadata loại đối tượng/platform.
- SBOM nguyên vẹn, document digest, phiên bản schema/profile và phạm vi.
- Bằng chứng nguồn/chứng thực và kết quả xác minh danh tính theo policy.
- Kết quả đối chiếu coverage, unknown và owner xử lý.
- Báo cáo assessment cùng dữ liệu/ruleset đã dùng, VEX và ngoại lệ liên quan.
- Quyết định gate, revision policy, release/deployment và lịch sử thay đổi.

Không cần nhét mọi báo cáo lỗ hổng vào bản kê gốc. Tách inventory với assessment giúp giữ lịch sử của một artifact trong khi cập nhật kiến thức về rủi ro. Chỉ mục tìm kiếm có thể được tái tạo, nhưng tài liệu và bằng chứng gốc cần được bảo toàn theo chính sách lưu giữ.

### 11.2. Phân quyền và bản chia sẻ

SBOM có thể lộ version nội bộ, cấu trúc sản phẩm, supplier hoặc metadata của môi trường build. Không coi SBOM mặc nhiên là dữ liệu công khai hay mặc nhiên là bí mật tuyệt đối; cần phân loại theo đối tượng nhận và mục đích.

Không đưa token repository, credential, URL có secret, private key, dữ liệu khách hàng hoặc toàn bộ biến môi trường vào tài liệu. Thông tin author có thể là danh tính tổ chức/dịch vụ theo hợp đồng, không cần thu thập dư dữ liệu cá nhân.

Nếu tạo bản dành cho đối tác bằng cách bỏ metadata nhạy cảm, phải quản lý đây là phiên bản/tài liệu được dẫn xuất. Không giữ nguyên chữ ký của bytes cũ rồi tuyên bố nó xác thực bytes đã sửa. Việc biên tập cũng không được che việc phạm vi hoặc dữ liệu nhận diện đã bị giảm, khiến người nhận hiểu sai tính đầy đủ.

### 11.3. Từ advisory tới deployment

Một luồng ứng phó có thể:

1. Tiếp nhận advisory và xác định ecosystem, định danh, khoảng version, độ chắc chắn của dữ liệu.
2. Truy vấn chỉ mục component và SBOM, giữ cả candidate/unknown cần điều tra.
3. Tìm artifact, platform, release và deployment đang dùng; không chỉ tìm branch source hiện tại.
4. Kiểm tra assessment/VEX đúng phạm vi và liên hệ owner xử lý theo quy trình.
5. Khắc phục, giảm thiểu hoặc phê duyệt rủi ro theo quyền; tạo bằng chứng cho artifact/điều kiện mới.
6. Xác nhận bản triển khai đã đổi và giữ lịch sử bản cũ để điều tra/rollback có kiểm soát.

Mục tiêu danh sách ban đầu trong 4 giờ là mục tiêu truy vết của ví dụ, không cam kết đã sửa mọi rủi ro trong 4 giờ. Nếu có platform thiếu inventory hoặc version chưa biết, báo rõ khoảng trống và owner thay vì loại chúng khỏi danh sách.

### 11.4. Audit và metric

Có thể theo dõi tỷ lệ artifact đủ bằng chứng trong phạm vi, số subject mismatch, component chưa xác định, chênh lệch đối chiếu, scanner lỗi, dữ liệu quá tuổi, finding bị chặn và ngoại lệ sắp hết hạn. Phải định nghĩa mẫu số của tỷ lệ coverage; số component lớn không tự chứng minh coverage tốt.

Audit cần đủ để tái dựng lý do quyết định, gồm subject/SBOM digest, nguồn, policy revision và trạng thái assessment. Hạn chế nhãn metric có cardinality cao; không đưa mọi component/version/artifact digest thành nhãn toàn cục nếu hệ thống không được thiết kế cho lượng giá trị đó. Chỉ mục tra cứu chi tiết và metric tổng hợp có vai trò khác nhau.

## 12. Ma trận kiểm thử nghiệm thu

Dùng artifact và advisory tổng hợp, khóa/danh tính thử, cùng nguồn dữ liệu được kiểm soát. Bộ fixture nên có cả trường hợp được phép và trường hợp thiếu bằng chứng; một gate từ chối tất cả không đáp ứng yêu cầu sử dụng SBOM.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-SBOM-01 | Tài liệu đúng profile; lượt khác sai schema, thiếu subject hoặc phiên bản không hỗ trợ | Bản đúng được đọc theo profile; bản sai không được coi là SBOM đủ điều kiện | SBOM-01, 02 |
| T-SBOM-02 | SBOM/bằng chứng đúng cho artifact A; sửa một byte để có artifact B nhưng giữ tên/tag | Subject mismatch; quyết định của A không áp cho B | SBOM-03 |
| T-SBOM-03 | SBOM chỉ cho một platform nhưng release có image/platform khác hoặc chỉ đưa digest index thay phạm vi được yêu cầu | Phát hiện thiếu phạm vi; không suy từ một SBOM sang mọi platform | SBOM-01, 03 |
| T-SBOM-04 | Sửa bytes tài liệu; dùng chứng thực đúng mật mã nhưng signer không thuộc danh tính được phép | Không chấp nhận bằng chứng cũ hoặc nguồn không được ủy quyền | SBOM-04 |
| T-SBOM-05 | Component trùng reference, thiếu version, sai ecosystem hoặc supplier chưa biết | Trùng/định danh sai bị phát hiện; unknown được giữ và xử lý theo policy, không bịa dữ liệu | SBOM-05 |
| T-SBOM-06 | Cạnh trỏ tới component không có; shared dependency; graph có vòng theo loại dữ liệu hỗ trợ | Không âm thầm bỏ cạnh; duyệt đủ theo phạm vi mà không lặp vô hạn | SBOM-06, 13 |
| T-SBOM-07 | Bỏ cả component parser và cạnh khỏi SBOM; artifact/resolve vẫn chứa parser. Thêm fixture thư viện copy/shade/native theo phạm vi | Đối chiếu tìm chênh lệch hoặc ghi unknown/blind spot cần xử lý; schema hợp lệ không đủ để pass | SBOM-07 |
| T-SBOM-08 | Generator lỗi hoặc output thiếu trong build mới; workspace còn SBOM build trước | Không dùng SBOM cũ như output mới; gate phân loại missing/subject mismatch đúng | SBOM-08, 11 |
| T-SBOM-09 | Scanner lỗi, timeout hoặc chạy trên dữ liệu quá 24 giờ theo hợp đồng ví dụ | ASSESSMENT_UNAVAILABLE hoặc trạng thái policy tương ứng; không báo không có finding | SBOM-09, 11 |
| T-SBOM-10 | VEX/ngoại lệ đúng advisory nhưng cho subject/cấu hình khác, thiếu căn cứ hoặc hết hạn | Không tự miễn trừ; giữ component/finding và yêu cầu đánh giá đúng phạm vi | SBOM-10 |
| T-SBOM-11 | Advisory tổng hợp khớp parser bắc cầu; lượt khác artifact hợp lệ, dữ liệu đủ và không có điều kiện chặn | Tìm đúng candidate/đường dependency; test dương tính đi qua gate theo policy | SBOM-05, 06, 09, 11 |
| T-SBOM-12 | Payload vượt 10 MiB sau giải nén, graph vượt quota, parse chậm hoặc reference ngoài yêu cầu tải URL | Giới hạn đầu vào/tài nguyên có hiệu lực; không tải tài nguyên ngoài hợp đồng | SBOM-13 |
| T-SBOM-13 | SBOM chứa secret/metadata nhạy cảm; người không có quyền tải; bản biên tập dùng chứng thực bản gốc | Chặn/làm sạch theo chính sách, từ chối truy cập trái quyền và không xác minh sai tài liệu đã đổi | SBOM-14 |
| T-SBOM-14 | Promote/rollback giữ tag nhưng đổi digest; assessment hoặc danh tính nguồn không còn đạt policy hiện hành | Kiểm tra lại đúng subject/phạm vi/quy tắc hiện hành; không phát hành dựa trên kết quả cũ không còn áp dụng | SBOM-03, 17 |
| T-SBOM-15 | Nạp plugin hoặc đổi package qua volume sau triển khai | Phát hiện/chặn hoặc cập nhật inventory và đánh giá theo hợp đồng; không dùng SBOM gốc như ảnh chụp runtime mới | SBOM-12 |
| T-SBOM-16 | Khôi phục kho bằng chứng và diễn tập advisory có nhiều release/platform, một số version unknown | Khôi phục được liên kết; danh sách ban đầu trong 4 giờ nêu cả khoảng trống và owner | SBOM-15, 16 |
| T-SBOM-17 | Thay tài liệu/artifact tại đường dẫn mutable sau kiểm tra nhưng trước promote | Không đưa đối tượng mới qua quyết định của đối tượng cũ; ràng buộc bất biến giữ tới deploy | SBOM-03, 04, 17 |
| T-SBOM-18 | Giả lập coverage gap, scan lỗi và exception approved; kiểm tra audit/metric | Lý do và revision đúng, không gộp thành PASS thông thường hoặc “clean”; không lộ secret | SBOM-11, 18 |

### 12.1. Acceptance criteria theo Given–When–Then

**AC-01 — Đúng subject và trường hợp hợp lệ.** Given artifact A bất biến, SBOM đủ profile/phạm vi, nguồn được phép và assessment đủ điều kiện không vi phạm policy. When gate đánh giá và promote. Then chỉ A được phép đi qua; audit liên kết đúng artifact digest, SBOM digest, policy revision và kết quả. Nếu chỉ thay artifact thành B khác bytes, Then quyết định của A không được tái dùng.

**AC-02 — Dependency bắc cầu không biến mất.** Given graph/đóng gói thử có `app → demo-http → demo-parser`. When SBOM bỏ parser và cả cạnh tới nó. Then kiểm tra schema có thể vẫn đạt nhưng kiểm tra coverage phải phát hiện chênh lệch hoặc phần thiếu bằng chứng; không công bố inventory đầy đủ cho phạm vi đó.

**AC-03 — Không nhầm thiếu đánh giá với sạch.** Given inventory đúng subject nhưng dữ liệu advisory quá tuổi hoặc scanner thất bại. When pipeline tạo quyết định. Then trạng thái phản ánh không đánh giá được theo policy; không tạo báo cáo “không tìm thấy lỗ hổng” thay cho lỗi. Ngoại lệ, nếu có, phải đúng quyền, phạm vi và thời hạn.

**AC-04 — Assessment có phạm vi.** Given VEX được phê duyệt cho một artifact/cấu hình cụ thể. When thay digest, cấu hình liên quan hoặc advisory vượt điều kiện assessment. Then không tự kế thừa trạng thái không ảnh hưởng; giữ component trong SBOM và đánh giá lại theo trigger. Không sửa inventory để làm finding biến mất.

**AC-05 — Truy vết và phục hồi.** Given các release/platform được liên kết tới SBOM và deployment, có một advisory thử khớp component. When diễn tập truy vấn rồi restore/rollback. Then danh sách ban đầu đáp ứng mục tiêu 4 giờ, gồm candidate/unknown và owner; bản phục hồi dùng đúng artifact–SBOM, còn quyết định rủi ro được kiểm tra theo policy hiện hành.

### 12.2. Bằng chứng cần lưu cho kiểm thử

Ghi loại artifact và digest đo thực tế, fixture SBOM, schema/profile, phương pháp tạo/đối chiếu, phiên bản công cụ, dữ liệu/ruleset assessment, policy revision, trạng thái mong đợi/thực tế và deployment/platform thử. Với giới hạn đầu vào, ghi tài nguyên và việc có/không tải tài nguyên ngoài. Với truy vấn sự cố, ghi cả trường hợp chưa xác định, không chỉ danh sách match chắc chắn.

Không dùng secret production để chứng minh kiểm thử chữ ký hoặc truy cập. Không chỉ kiểm tra HTTP thành công của cổng upload; cần kiểm tra tài liệu nào thực sự được ràng buộc với artifact nào và quyết định nào đã được áp dụng.

## 13. Truy vết từ rủi ro tới vòng đời phát triển

```text
Mục tiêu biết đúng thành phần của sản phẩm cần bảo vệ
  → SBR-xx: sai subject, bỏ thành phần, nguồn giả, dữ liệu cũ, drift runtime
  → SBOM-xx: phạm vi + điều kiện đạt + owner + hành vi khi không đạt
  → Pipeline tạo/đối chiếu, kho bằng chứng, gate và inventory deployment
  → T-SBOM-xx / AC-xx
  → Audit, phản ứng advisory, khắc phục và kiểm tra sau phục hồi
```

| Mục tiêu | Yêu cầu | Kiểm chứng tiêu biểu |
| --- | --- | --- |
| Đúng sản phẩm/artifact/platform | SBOM-01, 03, 17 | T-SBOM-02, 03, 14, 17; AC-01 |
| Không bỏ phần bắc cầu/khó nhận diện | SBOM-05, 06, 07 | T-SBOM-05, 06, 07; AC-02 |
| Nguồn và tài liệu không bị đánh tráo | SBOM-04, 08 | T-SBOM-04, 08, 17 |
| Đánh giá bằng dữ liệu đủ điều kiện | SBOM-09, 10, 11 | T-SBOM-09, 10, 11; AC-03, 04 |
| Không sai sau runtime change/restore | SBOM-12, 15, 17 | T-SBOM-14, 15, 16; AC-05 |
| Bảo vệ tài liệu và truy vết sự cố | SBOM-13, 14, 16, 18 | T-SBOM-12, 13, 16, 18 |

Khi đổi cách đóng gói, công cụ build, generator, schema/profile, trust của signer, nguồn advisory hoặc cơ chế nạp plugin, phải xem lại yêu cầu và test liên quan. Nếu generator phát hiện thành phần bị bỏ sót trước đây, cần xác định những quyết định cũ nào bị ảnh hưởng, thay vì chỉ làm mới tài liệu của release tiếp theo.

## 14. Lỗi thường gặp và bài tập áp dụng

| Cách làm | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Có file SBOM nên supply chain an toàn.” | Chưa chứng minh phạm vi, nguồn, subject hoặc chất lượng | Nghiệm thu các điều kiện cụ thể và giữ bằng chứng |
| “Lockfile chính là toàn bộ SBOM triển khai.” | Có thể bỏ thành phần đóng gói, OS/runtime hoặc nạp động | Đặc tả phạm vi và đối chiếu nhiều nguồn |
| “Tên/version giống nhau thì dùng lại SBOM.” | Artifact khác bytes/variant/platform có thể khác nội dung | Ràng buộc đúng digest và phạm vi |
| “Hash SBOM và artifact đều khớp nên nguồn đáng tin.” | Kẻ kiểm soát cùng nguồn có thể thay cả hai | Xác thực nguồn/chứng thực với gốc tin cậy được phép |
| “SBOM ký hợp lệ thì chắc chắn đầy đủ.” | Người có quyền ký vẫn có thể tạo inventory thiếu | Kiểm tra coverage và giới hạn nhận diện |
| “Scanner lỗi thì để danh sách finding rỗng.” | Tạo nghĩa sai về mức chắc chắn | Phân loại assessment unavailable, áp policy rõ |
| “VEX nói không ảnh hưởng nên xóa dependency.” | Làm sai inventory và mất truy vết | Giữ component; quản lý assessment riêng đúng phạm vi |
| “SBOM cũ một tháng phải sai.” | Nhầm tuổi tài liệu với thay đổi artifact và dữ liệu rủi ro | Theo dõi vòng đời inventory và assessment riêng |
| “Runtime cài thêm plugin không liên quan SBOM build.” | Phần mềm thực thi có thể đã đổi phạm vi | Kiểm soát hoặc cập nhật inventory trước sử dụng theo policy |

Một nhóm phát hành container bằng tag có thể ghi đè. SBOM được tạo từ dependency trực tiếp trong source, không có OS/runtime. Pipeline chỉ kiểm tra JSON đọc được và bỏ qua lỗi scanner. Nhà cung cấp gửi một VEX không nêu artifact digest; đội vận hành áp nó cho mọi môi trường. Khi có advisory mới, đội chỉ tìm trên nhánh source hiện tại.

Hãy thực hiện:

1. Chỉ ra ít nhất sáu kịch bản rủi ro và bất biến bị vi phạm.
2. Định nghĩa subject, platform và phạm vi của SBOM ứng dụng, image và build.
3. Viết sáu yêu cầu có ID, owner, điều kiện đạt, lỗi và bằng chứng kiểm thử.
4. Thiết kế liên kết artifact–SBOM–chứng thực–assessment tới deployment.
5. Nêu cách phát hiện dependency bắc cầu, thư viện đóng gói lại và phần chưa nhận diện.
6. Thiết kế test phân biệt không có finding với không đánh giá được, cùng test cho VEX sai phạm vi.
7. Diễn giải quy trình tìm release/deployment liên quan advisory, gồm candidate chưa chắc chắn và dữ liệu cần giữ khi rollback.

Trước khi chấp nhận đặc tả, kiểm tra:

- Subject, digest, platform và phạm vi đã rõ chưa?
- Schema/profile, nguồn tạo, công cụ và giới hạn nhận diện có được ghi chưa?
- Thành phần, định danh, quan hệ và unknown có được kiểm tra/đối chiếu chưa?
- Nguồn/chứng thực có ràng buộc đúng tài liệu và danh tính được ủy quyền không?
- Artifact/SBOM có bất biến từ gate tới deploy không?
- Dữ liệu lỗ hổng, assessment và ngoại lệ có nguồn, độ mới và phạm vi không?
- Lỗi công cụ có bị tách khỏi kết quả không tìm thấy finding không?
- Runtime change, phân quyền chia sẻ, lưu giữ và khôi phục có owner và test không?
- Một advisory có truy ngược được tới đúng release, platform và deployment không?

SBOM trở thành bằng chứng hữu ích khi tổ chức biết nó mô tả đối tượng nào, quan sát được đến đâu, tin nguồn nào và dùng nó trong quyết định nào có thể kiểm chứng.
