# Code Quality Static Analysis — Dependency Analysis

Dependency Analysis là quá trình phân tích tĩnh các quan hệ phụ thuộc giữa class, package, module và thư viện trong dự án Java. Bằng cách quan sát đồ thị phụ thuộc, người phát triển có thể phát hiện vòng phụ thuộc, liên kết chặt, sự vượt ranh giới kiến trúc và những thư viện được đưa vào gián tiếp.

Module dành cho người học Java muốn kiểm soát cấu trúc mã và sự phụ thuộc của dự án. Lộ trình đi từ cách đọc đồ thị, dùng `jdeps` để khảo sát class/package, dùng Gradle để truy vết thư viện, đến viết quy tắc với ArchUnit, sửa vi phạm và đưa kiểm tra vào CI. Sau module, người học có thể giải thích kết quả phân tích và chủ động giảm các phụ thuộc không mong muốn.