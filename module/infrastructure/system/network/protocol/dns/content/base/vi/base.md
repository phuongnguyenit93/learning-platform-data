# Network Protocol DNS

Domain Name System (DNS) là hệ thống phân giải tên miền, giúp ứng dụng tìm địa chỉ IP và những thông tin dịch vụ cần thiết để kết nối. DNS hoạt động theo cấu trúc phân cấp: nhiều máy chủ và resolver phối hợp để trả lời truy vấn, trong khi bộ nhớ đệm giúp giảm độ trễ và tải truy vấn.

Module này dẫn bạn qua vai trò DNS, cây tên miền và zone, luồng phân giải, các loại bản ghi phổ biến, cache và TTL, trách nhiệm của resolver với máy chủ có thẩm quyền, rồi đến truyền tải và bảo mật. Phần cuối hướng dẫn quan sát truy vấn, đọc phản hồi và khoanh vùng lỗi bằng các công cụ cơ bản như `dig` hoặc `nslookup`.

Nội dung dành cho người học mạng máy tính, lập trình backend hoặc bắt đầu vận hành hệ thống. Sau khi học, bạn có thể lý giải cách tên miền được phân giải, đọc bản ghi phù hợp, nhận biết khác biệt giữa DNSSEC và DNS over HTTPS, và kiểm tra các lỗi như NXDOMAIN, SERVFAIL hoặc thay đổi bản ghi chưa hết thời gian cache.