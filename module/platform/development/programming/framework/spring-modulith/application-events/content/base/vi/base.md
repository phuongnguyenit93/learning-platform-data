# Spring Modulith Application Events

Spring Modulith khuyến khích các module nghiệp vụ trao đổi thông tin bằng application event để giảm phụ thuộc trực tiếp. Module này giới thiệu cách phát sự kiện qua `ApplicationEventPublisher`, nhận sự kiện với `@ApplicationModuleListener`, và hiểu tác động của transaction cùng xử lý bất đồng bộ. Mục tiêu là thiết kế luồng phối hợp giữa các module rõ ràng, có thể kiểm chứng và phục hồi khi xảy ra lỗi.

Người học nên biết Java, Spring Boot, Spring events và giao dịch cơ bản. Lộ trình đi từ sự kiện nghiệp vụ, publish/subscribe giữa module, đến listener và transaction. Tiếp theo là Event Publication Registry để theo dõi việc giao sự kiện, xử lý sự kiện lỗi và phát lại, externalization ra broker khi cần, cuối cùng kiểm thử bằng `PublishedEvents` và `Scenario`.

Hoàn thành module, bạn có thể triển khai giao tiếp sự kiện giữa các module trong ứng dụng Spring, phân biệt luồng đồng bộ và bất đồng bộ, nhận biết rủi ro mất hoặc xử lý lặp sự kiện, và xây dựng kiểm thử bảo đảm hành vi nghiệp vụ. Các chi tiết về trạng thái publication và API khôi phục phụ thuộc phiên bản Spring Modulith đang dùng.