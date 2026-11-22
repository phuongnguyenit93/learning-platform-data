# Spring Ldap

Spring LDAP là thư viện trong hệ sinh thái Spring giúp ứng dụng Java làm việc với dịch vụ thư mục LDAP mà không phải tự quản lý phần lớn chi tiết JNDI, tài nguyên và xử lý ngoại lệ. LDAP lưu các *entry* theo cấu trúc phân cấp, định danh bằng DN và tra cứu bằng filter; vì thế cách tư duy với LDAP khác với truy vấn bảng trong cơ sở dữ liệu quan hệ.

Module dành cho người đã có kiến thức cơ bản về Java, Spring và kết nối dịch vụ bên ngoài. Bạn sẽ đi từ mô hình thư mục, DN và schema đến cấu hình `LdapContextSource`, tra cứu bằng `LdapClient` hoặc `LdapTemplate`, xây bộ lọc an toàn, thao tác entry, ánh xạ đối tượng qua ODM/Repository, rồi xác thực và bảo mật kết nối. Phần cuối giới thiệu pooling, giới hạn của transaction bù phía client và kiểm thử với máy chủ LDAP nhúng.

Qua tám mốc, người học có thể xây dựng luồng truy cập thư mục dễ duy trì, phân biệt thao tác truy vấn với xác thực, tránh ghép filter thiếu an toàn, kiểm tra mapping và xử lý các tình huống lỗi thường gặp. Trọng tâm là nền tảng Spring LDAP, không đồng nhất nó với toàn bộ cơ chế xác thực và phân quyền của Spring Security.