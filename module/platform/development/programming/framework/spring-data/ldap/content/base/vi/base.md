# Spring Data Ldap

Spring Data LDAP giúp ứng dụng Spring truy cập dịch vụ thư mục LDAP bằng mô hình repository quen thuộc. Khác với cơ sở dữ liệu quan hệ, LDAP lưu dữ liệu dưới dạng các entry phân cấp, được xác định bởi Distinguished Name (DN) và mô tả bằng thuộc tính cùng objectClass. Module này tập trung vào cách hiểu cấu trúc thư mục, ánh xạ entry sang đối tượng Java và truy xuất dữ liệu một cách đúng đắn.

Lộ trình một cấp gồm tám mốc: bắt đầu với DN và schema, thiết lập kết nối Spring, rồi tìm hiểu Object-Directory Mapping và thao tác CRUD bằng repository. Những mốc tiếp theo hướng dẫn query methods, @Query, LdapQuery và LdapTemplate; sau đó làm rõ giới hạn của LDAP, cách sử dụng bộ lọc an toàn và kiểm thử với directory riêng.

Module dành cho người đã biết Java, Spring và thao tác dữ liệu cơ bản. Sau khi học, bạn có thể cấu hình Spring Data LDAP, định nghĩa entry và repository, thực hiện truy vấn có tham số, lý giải những giới hạn đặc thù của LDAP và kiểm chứng hoạt động trên môi trường kiểm thử.