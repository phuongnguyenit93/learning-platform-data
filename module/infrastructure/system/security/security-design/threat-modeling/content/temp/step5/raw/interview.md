Anh/chị xác định mục tiêu, phạm vi và mức độ chi tiết phù hợp cho một hoạt động threat modeling như thế nào?
Những thay đổi nào về kiến trúc, dữ liệu, người dùng hoặc môi trường triển khai khiến cần lập mới hay cập nhật threat model?
Anh/chị lựa chọn hệ thống, thành phần và luồng nghiệp vụ ưu tiên mô hình hóa dựa trên mức độ quan trọng và rủi ro ra sao?
Làm thế nào xác định ranh giới hệ thống và các giả định cần ghi nhận trước khi bắt đầu phân tích mối đe dọa?
Anh/chị kiểm kê tài sản cần bảo vệ, bao gồm dữ liệu, credential, dịch vụ, cấu hình và năng lực vận hành như thế nào?
Những thuộc tính nào giúp phân loại tài sản theo tính bí mật, toàn vẹn, khả dụng, quyền riêng tư và tác động kinh doanh?
Anh/chị xác định tác nhân bên ngoài, người dùng nội bộ, quản trị viên, đối tác và workload có thể tương tác với hệ thống ra sao?
Làm thế nào đánh giá năng lực, động cơ, nguồn lực và mức độ tiếp cận của từng nhóm tác nhân tấn công?
Anh/chị xây dựng data flow diagram để thể hiện tiến trình, kho dữ liệu, luồng truyền và ranh giới tin cậy như thế nào?
Những chi tiết nào trong DFD thường bị bỏ sót nhưng có thể làm thay đổi kết luận threat modeling?
Anh/chị xác định trust boundary tại gateway, service-to-service, database, cloud account và nhà cung cấp như thế nào?
Làm thế nào nhận diện dữ liệu hoặc lệnh đi qua ranh giới tin cậy mà chưa được xác thực, kiểm tra hoặc giới hạn phù hợp?
Anh/chị kiểm tra tính đầy đủ của DFD bằng cách đối chiếu với kiến trúc triển khai, cấu hình mạng và telemetry ra sao?
Anh/chị áp dụng STRIDE cho từng thành phần và luồng dữ liệu theo quy trình nào để tránh bỏ sót loại mối đe dọa?
Khi phân tích Spoofing, anh/chị xác định các danh tính, credential hoặc cơ chế xác thực có thể bị giả mạo như thế nào?
Anh/chị đánh giá nguy cơ Tampering đối với dữ liệu, thông điệp, cấu hình và artifact trong quá trình truyền hoặc lưu trữ ra sao?
Những tình huống Repudiation nào cần xem xét khi hệ thống thiếu bằng chứng đáng tin cậy về hành động và nguồn phát sinh?
Anh/chị xác định các điểm có thể dẫn tới Information Disclosure qua API, log, cache, backup hoặc thông báo lỗi như thế nào?
Làm thế nào đánh giá Denial of Service đối với tài nguyên tính toán, hàng đợi, dependency và các dịch vụ dùng chung?
Anh/chị nhận diện các đường Elevation of Privilege từ quyền thấp tới quyền quản trị hoặc truy cập dữ liệu nhạy cảm ra sao?
Khi một thành phần có nhiều loại luồng dữ liệu, anh/chị tránh áp dụng STRIDE máy móc và ưu tiên theo ngữ cảnh như thế nào?
Anh/chị lựa chọn LINDDUN khi mục tiêu phân tích tập trung vào quyền riêng tư và dữ liệu cá nhân trong trường hợp nào?
Làm thế nào nhận diện Linkability khi nhiều tập dữ liệu hoặc sự kiện riêng lẻ có thể liên kết thành hồ sơ của một cá nhân?
Anh/chị đánh giá Identifiability từ các thuộc tính trực tiếp, gián tiếp và dữ liệu phụ trợ có thể kết hợp ra sao?
Những rủi ro Non-repudiation nào xuất hiện khi người dùng không thể kiểm soát hoặc phủ nhận việc ghi nhận hành vi của mình?
Anh/chị xác định nguy cơ Detectability khi một bên có thể suy ra sự hiện diện của cá nhân hoặc thuộc tính nhạy cảm qua phản hồi hệ thống như thế nào?
Làm thế nào phân tích Information Disclosure và Unawareness trong các luồng thu thập, sử dụng hoặc chia sẻ dữ liệu cá nhân?
Anh/chị đánh giá Non-compliance khi mục đích xử lý, thời hạn lưu giữ hoặc cơ chế đồng ý không phù hợp với cam kết và nghĩa vụ áp dụng ra sao?
Khi STRIDE và LINDDUN cùng chỉ ra rủi ro trên một luồng dữ liệu, anh/chị hợp nhất kết quả và tránh đếm trùng như thế nào?
Anh/chị xây dựng attack tree từ mục tiêu của tác nhân tới các bước, điều kiện và nhánh tấn công khả thi ra sao?
Làm thế nào phân biệt một attack path lý thuyết với đường tấn công có thể thực hiện trong kiến trúc và cấu hình hiện tại?
Anh/chị xác định các tiền điều kiện, quyền ban đầu và phụ thuộc cần thiết cho từng nhánh trong attack tree như thế nào?
Những cách nào giúp phát hiện đường tấn công kết hợp nhiều điểm yếu nhỏ nhưng dẫn tới tác động lớn?
Anh/chị xây dựng abuse case từ hành vi sử dụng sai mục đích của người dùng hợp lệ hoặc tài khoản nội bộ như thế nào?
Làm thế nào mô tả misuse case để làm rõ tài sản bị ảnh hưởng, hành vi lạm dụng và kết quả không mong muốn?
Anh/chị kết hợp abuse case với user story và yêu cầu bảo mật để các tình huống lạm dụng được xem xét từ đầu như thế nào?
Những nguồn thông tin nào giúp kiểm chứng threat model phản ánh đúng hành vi của hệ thống thay vì chỉ dựa trên sơ đồ thiết kế?
Anh/chị đánh giá khả năng xảy ra của một mối đe dọa dựa trên mức phơi lộ, năng lực tác nhân, điều kiện khai thác và kiểm soát hiện có ra sao?
Làm thế nào ước lượng tác động theo tính bí mật, toàn vẹn, khả dụng, quyền riêng tư, an toàn và gián đoạn nghiệp vụ?
Anh/chị lựa chọn thang điểm và tiêu chí risk scoring để các nhóm có thể đánh giá nhất quán như thế nào?
Khi thiếu dữ liệu định lượng về khả năng xảy ra, anh/chị biểu đạt độ bất định và tránh tạo cảm giác chính xác giả ra sao?
Anh/chị phân biệt mức độ nghiêm trọng của một điểm yếu với mức rủi ro của mối đe dọa trong bối cảnh triển khai như thế nào?
Làm thế nào ưu tiên các mối đe dọa có thể kết hợp thành chuỗi tấn công hoặc ảnh hưởng nhiều tài sản cùng lúc?
Anh/chị xác định rủi ro còn lại sau mitigation và điều kiện cần để chấp nhận rủi ro đó như thế nào?
Những tiêu chí nào giúp lựa chọn giữa loại bỏ tính năng, giảm khả năng khai thác, giảm tác động, chuyển giao hoặc chấp nhận rủi ro?
Anh/chị chuyển một mối đe dọa đã xác định thành security requirement và tiêu chí kiểm chứng cụ thể ra sao?
Làm thế nào lựa chọn preventive, detective và responsive controls phù hợp với nguyên nhân và đường tấn công?
Anh/chị đánh giá liệu một mitigation có thực sự ngắt attack path hay chỉ làm tăng chi phí khai thác như thế nào?
Khi mitigation tạo ra rủi ro mới hoặc ảnh hưởng khả dụng, anh/chị phân tích trade-off và phương án thay thế ra sao?
Anh/chị xác định chủ sở hữu, thời hạn và bằng chứng hoàn thành cho từng biện pháp giảm thiểu như thế nào?
Làm thế nào kiểm chứng control đã được triển khai đúng và hoạt động hiệu quả trong cấu hình thực tế?
Anh/chị thiết kế test case để kiểm tra các giả thuyết tấn công, abuse case và điều kiện vượt qua trust boundary ra sao?
Những phương pháp nào giúp kết hợp threat modeling với code review, security testing, penetration testing và red team?
Anh/chị xử lý mối đe dọa chưa thể tái hiện trong môi trường thử nghiệm nhưng có tác động tiềm tàng lớn như thế nào?
Làm thế nào bảo đảm kết quả threat modeling được truy vết tới yêu cầu, quyết định kiến trúc, control và test evidence?
Anh/chị tổ chức workshop threat modeling để các nhóm kỹ thuật, nghiệp vụ, vận hành và bảo mật cùng phát hiện giả định sai ra sao?
Những kỹ thuật nào giúp tránh thiên kiến của nhóm thiết kế khi tự đánh giá các mối đe dọa đối với hệ thống của mình?
Anh/chị quyết định khi nào cần chuyên gia độc lập hoặc red team tham gia rà soát threat model như thế nào?
Làm thế nào cập nhật threat model khi xuất hiện CVE mới, kỹ thuật tấn công mới hoặc thay đổi năng lực của đối thủ?
Anh/chị theo dõi thay đổi trong cloud service, dependency, API, network route và workload identity để phát hiện threat mới ra sao?
Những thay đổi nào trong data flow, trust boundary hoặc quyền truy cập cần kích hoạt đánh giá lại ngay trước khi phát hành?
Anh/chị quản lý phiên bản, giả định, quyết định và lịch sử thay đổi của threat model để người khác có thể kiểm tra lại như thế nào?
Làm thế nào đánh giá mức độ bao phủ của threat model và nhận diện các thành phần hoặc luồng chưa được phân tích?
Anh/chị trình bày các mối đe dọa ưu tiên, tác động kinh doanh và rủi ro còn lại cho lãnh đạo theo cách hỗ trợ quyết định ra sao?
Những chỉ số nào phản ánh chất lượng threat modeling ngoài số lượng mối đe dọa được ghi nhận?
Anh/chị đo thời gian xử lý mitigation, tỷ lệ attack path bị ngắt và số phát hiện tái diễn như thế nào?
Làm thế nào tích hợp lessons learned từ incident, bug bounty và penetration test vào lần threat modeling tiếp theo?
Anh/chị xác định khi nào threat model đã đủ cập nhật để hỗ trợ quyết định go-live hoặc thay đổi kiến trúc như thế nào?
