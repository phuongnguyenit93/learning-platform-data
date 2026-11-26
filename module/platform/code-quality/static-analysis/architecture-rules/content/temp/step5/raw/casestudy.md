Trong hệ thống đặt hàng Java theo ba tầng, một controller mới gọi trực tiếp repository để lấy dữ liệu cho màn hình; ArchUnit báo vi phạm quy tắc controller chỉ phụ thuộc service.
Một nhóm theo kiến trúc hexagonal phát hiện lớp domain import trực tiếp annotation của Spring để tận dụng dependency injection, khiến mô hình nghiệp vụ không còn độc lập framework.
API trả về thực thể JPA từ tầng persistence thay vì kiểu dữ liệu công khai; khi schema database đổi, client cũng phải thay đổi dù hợp đồng REST ban đầu không yêu cầu.
Một nhóm đổi tên package theo domain nghiệp vụ nhưng bộ quy tắc ArchUnit vẫn dùng mẫu tên package cũ, dẫn đến các lớp mới không còn được kiểm tra ràng buộc phụ thuộc.
Trong repository nhiều module, module billing chỉ được dùng giao diện public của module customer nhưng một developer import lớp implementation nội bộ để lấy nhanh thông tin tài khoản.
Bộ kiểm thử kiến trúc chỉ quét package của API gateway; một module Java mới chứa xử lý nghiệp vụ không xuất hiện trong tập lớp được ArchUnit kiểm tra ở CI.
Hai module order và payment bắt đầu gọi service của nhau sau nhiều lần thêm tính năng hoàn tiền, tạo chu trình phụ thuộc khiến việc xây dựng và thử nghiệm từng module trở nên khó khăn.
Trong kiến trúc ports and adapters, một adapter nhận sự kiện Kafka lại dùng DTO của REST controller để tái sử dụng mapping, khiến thay đổi giao diện HTTP ảnh hưởng luồng sự kiện.
Một thư viện Java công bố interface công khai nhưng tham số của interface lại là kiểu dữ liệu nằm trong package internal; ứng dụng khác buộc phải phụ thuộc vào chi tiết triển khai.
Nhóm gom tiện ích dùng chung vào package common; dần dần package này import các service nghiệp vụ và trở thành mắt xích mới của nhiều chu trình phụ thuộc.
Quy tắc kiến trúc cấm controller sử dụng lớp persistence, nhưng các test helper trong package test cũng bị tính vào tập lớp khiến pipeline báo hàng loạt vi phạm khó phân loại.
Repository lâu năm có danh sách ngoại lệ kiến trúc cho module legacy; một thay đổi mở rộng mẫu miễn trừ khiến cả những vi phạm mới cũng không còn bị ArchUnit phát hiện.
CI hiển thị lỗi kiểm thử kiến trúc chỉ với tên lớp mà không nêu ràng buộc nào bị phá vỡ, khiến reviewer khó xác định trách nhiệm và mức độ nghiêm trọng của thay đổi.
Nhóm phụ thuộc vào kiến trúc Java module để giới hạn API, nhưng mã của một module khác vẫn truy cập package implementation thông qua cấu hình build riêng và bản đóng gói trở nên khó quản lý.
Dự án sử dụng annotation processor sinh lớp adapter trong quá trình build; các lớp sinh ra xuất hiện trong kết quả quét ArchUnit và tạo cảnh báo phụ thuộc mà lập trình viên không trực tiếp viết.
Ứng dụng Maven nhiều module có kiểm thử ArchUnit tại một module kiểm thử chung, nhưng job CI chỉ chạy test của module thay đổi nên một vi phạm liên module lọt qua pull request.
Trong dự án Gradle, đội platform đặt quy tắc kiến trúc trong convention plugin nhưng một service tự thêm bộ quy tắc cục bộ với allowlist khác, khiến kết quả kiểm tra giữa các service không nhất quán.
Một quy tắc cấm tầng nghiệp vụ phụ thuộc hạ tầng báo lỗi vì lớp business dùng trực tiếp logger của thư viện cụ thể; nhóm phải xem phạm vi ràng buộc có phù hợp thiết kế đã thống nhất hay không.
Nhóm chuyển từ gọi trực tiếp giữa các domain sang giao tiếp bằng sự kiện; các package cũ và mới cùng tồn tại khiến kiểm thử kiến trúc liên tục báo vi phạm trong giai đoạn di trú.
Trong một microservice Java, service A chỉ được sử dụng API công khai của B nhưng một thư viện tiện ích được chia sẻ lại gián tiếp import lớp internal của B qua dependency truyền tiếp.
Một thành viên di chuyển các lớp sang package mới để tuân theo chuẩn tên nhưng vô tình tạo vòng phụ thuộc giữa application và infrastructure mà test hành vi không phát hiện.
Trong một hệ thống xử lý đơn hàng, lớp mapper của tầng application lại dùng hằng số từ adapter database; quy tắc hướng phụ thuộc cho rằng chi tiết lưu trữ đã rò sang nghiệp vụ.
Nhóm công bố sơ đồ phụ thuộc package trong tài liệu thiết kế, nhưng sau một quý các kết nối thực tế đã đổi vì nhiều pull request nhỏ không chạy kiểm thử kiến trúc trước khi merge.
ArchUnit phát hiện package báo cáo phụ thuộc vào package quản trị người dùng thông qua lớp enum dùng chung; reviewer tranh luận liệu đây là hợp đồng domain hay sự phụ thuộc chéo không chủ đích.
Một nhánh cải tổ code gộp các package domain nhỏ thành một package lớn, làm các quy tắc dựa trên tên package không còn phân biệt được ranh giới chức năng.
Trong quá trình viết kiểm thử cho quy tắc layered architecture, người duy trì dùng phạm vi quét quá rộng và vô tình áp đặt ràng buộc sản xuất lên lớp mock và fixture của test.
Một đội sử dụng Maven để chạy kiểm thử kiến trúc trong giai đoạn test nhưng pipeline release lại bỏ qua test nhằm rút ngắn thời gian, khiến artifact được phát hành mà không có kết quả kiểm tra ArchUnit.
Module inventory tích hợp thư viện bên thứ ba cung cấp model và service riêng; một lớp domain core import trực tiếp service của thư viện đó, phá vỡ quy tắc phụ thuộc hạ tầng qua cổng giao tiếp.
Quy tắc chỉ cho phép lớp trong package api được tham chiếu từ module ngoài đã được thêm vào CI, nhưng tên package api không đồng nhất giữa các module và cảnh báo xuất hiện khác nhau.
Repository doanh nghiệp có hàng nghìn lớp Java và nhiều quy tắc phụ thuộc; sau khi bổ sung ArchUnit, thời gian chạy test CI tăng đáng kể và nhóm phải quyết định mức kiểm tra phù hợp cho pull request.
