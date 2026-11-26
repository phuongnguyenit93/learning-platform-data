Câu 1. Spring Boot muốn sử dụng Spring Data LDAP repository, dependency nào phù hợp?
A. Thêm `spring-boot-starter-data-rest` thay LDAP client.
B. Thêm `spring-boot-starter-data-jdbc` cho LDAP entries.
C. Thêm `spring-boot-starter-data-jpa` cùng LDAP driver.
D. Thêm `spring-boot-starter-data-ldap` vào ứng dụng.
Đáp án đúng: D

Câu 2. Với DN `uid=mai,ou=people,dc=example,dc=org`, DN biểu diễn điều gì?
A. Tên objectClass quyết định thuộc tính mà entry được có.
B. Đường tên phân biệt xác định entry trong cây LDAP.
C. Địa chỉ server LDAP để client mở kết nối directory.
D. Giá trị mật khẩu dùng xác thực entry khi LDAP bind.
Đáp án đúng: B

Câu 3. Trong DN `uid=mai,ou=people,dc=example,dc=org`, RDN đầu tiên là gì?
A. Thành phần `dc=org` định danh entry dưới `ou=people`.
B. Thành phần `ou=people` định danh thuộc tính mail.
C. Thành phần `uid=mai` định danh entry trong parent.
D. Toàn chuỗi DN được xem là một attribute đơn nhất.
Đáp án đúng: C

Câu 4. Khi cấu hình `spring.ldap.base=dc=example,dc=org`, chức năng chính là gì?
A. Đặt host LDAP cần kết nối để tìm server trong DNS.
B. Đặt tên credential account được dùng cho simple bind.
C. Đặt objectClass mặc định cho entity mới tạo bằng API.
D. Đặt base DN để tạo ngữ cảnh truy cập LDAP theo cây.
Đáp án đúng: D

Câu 5. Muốn tìm entry dưới `ou=people` kể cả các OU con, search scope nào đúng?
A. Dùng one-level scope ở DN `ou=people,...`.
B. Dùng subtree scope với base DN `ou=people,...`.
C. Dùng object scope ở DN `ou=people,...`.
D. Dùng base-object scope kết hợp size limit lớn.
Đáp án đúng: B

Câu 6. Trong LDAP entry, thuộc tính `objectClass` có vai trò nào?
A. Thiết lập thứ tự xếp hạng entry khi truy vấn theo filter.
B. Chọn connection pool của ứng dụng để tìm LDAP server.
C. Xác định các lớp schema và tập thuộc tính entry hợp lệ.
D. Xác định timeout truy vấn của entry trong cùng một OU.
Đáp án đúng: C

Câu 7. Khi tạo entry `inetOrgPerson`, cặp thuộc tính nào thường bắt buộc do schema kế thừa?
A. Cần `uid` và `mail` vì đều là ID đăng nhập.
B. Cần `manager` và `departmentNumber` để tổ chức.
C. Cần `cn` và `sn` theo lớp schema `person`.
D. Cần `telephoneNumber` và `mobile` để liên lạc.
Đáp án đúng: C

Câu 8. Annotation Spring Data LDAP nào đánh dấu class được ánh xạ thành entry?
A. Dùng `@Entity` theo mapping Spring Data JPA.
B. Dùng `@Document` theo mapping Spring Data MongoDB.
C. Dùng `@Table` theo mapping Spring Data JDBC.
D. Dùng `@Entry` với base và objectClasses thích hợp.
Đáp án đúng: D

Câu 9. Trong Spring Data LDAP, field chứa DN của entry thường được đánh dấu thế nào?
A. Gắn `@PrimaryKey` cho field Base DN của entity.
B. Gắn `@Id` cho field `Name` đại diện DN entry.
C. Gắn `@GeneratedValue` cho field String chứa DN.
D. Gắn `@Version` cho field RDN để ánh xạ thư mục.
Đáp án đúng: B

Câu 10. Muốn ánh xạ thuộc tính LDAP `givenName` tới field Java, cách nào phù hợp?
A. Dùng `@Id("givenName")` để ánh xạ attribute.
B. Dùng `@Attribute(name = "givenName")` trên field.
C. Dùng `@DnAttribute("givenName")` để map entry value.
D. Dùng `@Entry("givenName")` để ánh xạ attribute.
Đáp án đúng: B

Câu 11. Trong entity, `@DnAttribute("uid")` hỗ trợ mục đích nào?
A. Ánh xạ giá trị `uid` xuất hiện trong DN của entry.
B. Ghi `uid` vào server credentials để thực hiện bind.
C. Định nghĩa LDAP search base mới cho mỗi truy vấn.
D. Ánh xạ `uid` thành objectClass bắt buộc của entry.
Đáp án đúng: A

Câu 12. Một field Java chỉ phục vụ UI, không cần lưu trong LDAP entry; nên gắn gì?
A. Đặt `@Transient` để loại field khỏi mapping persistent.
B. Đặt `@Attribute` để schema tự bỏ qua field khi ghi.
C. Đặt `@Entry` để field chỉ được đọc từ local cache.
D. Đặt `@DnAttribute` để field không bị LDAP search trả.
Đáp án đúng: A

Câu 13. Một attribute LDAP có thể có nhiều giá trị, kiểu field Java nào phù hợp?
A. Dùng `Long` và lấy số lượng value của attribute.
B. Dùng collection như `List<String>` cho các giá trị.
C. Dùng `Name` và ghép mọi value vào DN của entry.
D. Dùng `Boolean` và chọn value đầu làm kết quả.
Đáp án đúng: B

Câu 14. Để tạo repository CRUD cho LDAP entry có ID kiểu `Name`, cách nào phù hợp?
A. Cho interface kế thừa `JpaRepository<Person, Long>`.
B. Cho interface kế thừa `MongoRepository<Person, String>`.
C. Cho interface kế thừa `CassandraRepository<Person, UUID>`.
D. Cho interface kế thừa `CrudRepository<Person, Name>`.
Đáp án đúng: D

Câu 15. Repository có entity `Person` với field `mail`; method nào tận dụng derived query?
A. Định nghĩa `findByMail(String mail)` theo property.
B. Định nghĩa `findByObjectClass(Long mail)` cho email.
C. Định nghĩa `findByBaseDn()` để mặc định tìm mail.
D. Định nghĩa `findMailByDn(String mail)` như câu LDAP DN.
Đáp án đúng: A

Câu 16. Cần LDAP search với bộ lọc động và mapper riêng, thành phần Spring nào phù hợp?
A. Sử dụng `LdapTemplate` với query và entry mapper.
B. Sử dụng `JpaTemplate` với query trên LDAP server.
C. Sử dụng `MongoTemplate` với filter LDAP dạng BSON.
D. Sử dụng `JdbcTemplate` và SQL WHERE trên LDAP DN.
Đáp án đúng: A

Câu 17. Khi tìm `uid` từ dữ liệu nhập của người dùng, cách dựng filter nào an toàn?
A. Đưa input vào DN chưa escape rồi dùng làm filter.
B. Nối chuỗi `"(uid=" + input + ")"` rồi search LDAP.
C. Dùng `LdapQueryBuilder` với `.where("uid").is(input)`.
D. Chèn input vào chuỗi `(&(uid=...)(mail=...))` thô.
Đáp án đúng: C

Câu 18. Vì sao nối trực tiếp input vào chuỗi filter LDAP là rủi ro bảo mật?
A. Input chứa ký tự đặc biệt có thể thay cấu trúc filter.
B. Input dài làm schema tự chuyển thành bộ lọc object scope.
C. Input chứa dấu cách khiến mọi entry bị đổi objectClass.
D. Input chứa Unicode làm server bỏ qua toàn bộ search base.
Đáp án đúng: A

Câu 19. Khi tạo DN từ RDN do người dùng nhập, cách nào phù hợp?
A. Dùng `LdapNameBuilder` để xử lý RDN đúng quy tắc.
B. Dùng `LdapQueryBuilder.where()` để tạo DN khi ghi.
C. Dùng filter escape rồi ghép trực tiếp thành DN hoàn chỉnh.
D. Dùng phép nối `uid=` với input rồi bỏ kiểm tra DN.
Đáp án đúng: A

Câu 20. Muốn kiểm tra mật khẩu người dùng qua LDAP, cơ chế nào thực sự xác minh credential?
A. Đọc objectClass có `person` rồi cấp session cho user.
B. So sánh `cn` khớp username rồi coi là đăng nhập hợp lệ.
C. Xác nhận có entry với `uid` khớp rồi cho phép đăng nhập.
D. Thực hiện bind bằng DN người dùng và mật khẩu được cung cấp.
Đáp án đúng: D

Câu 21. Trong Spring LDAP, `ContextSource` chủ yếu đảm nhiệm việc gì?
A. Cung cấp mapping JSON của LDAP entry về REST API.
B. Cung cấp distributed transaction cho nhiều LDAP server.
C. Cung cấp LDAP context/kết nối với cấu hình xác thực.
D. Cung cấp repository query method từ tên field Java.
Đáp án đúng: C

Câu 22. Để dùng LDAPS, cấu hình kết nối nào phù hợp hơn?
A. Dùng `http://` tới LDAP server kèm Basic authentication.
B. Dùng `ldaps://` nhưng tắt xác minh hostname khi deploy.
C. Dùng `ldap://` và coi nó được mã hóa vì có password.
D. Dùng `ldaps://` cùng kiểm tra certificate của máy chủ.
Đáp án đúng: D

Câu 23. Nếu dùng StartTLS cho LDAP, client nên thực hiện điều gì?
A. Nâng kết nối LDAP sang TLS trước khi truyền credential.
B. Chỉ mã hóa mật khẩu ứng dụng mà để LDAP session plaintext.
C. Chuyển kết nối LDAP thành HTTP/2 sau khi bind thành công.
D. Gửi credential trước rồi bật TLS sau các thao tác ghi.
Đáp án đúng: A

Câu 24. Service account cho ứng dụng chỉ cần tìm người dùng; quyền nào nên được cấp?
A. Quyền write và delete trên toàn bộ directory tree.
B. Quyền thay mật khẩu cho mọi user khi search entry.
C. Quyền quản trị schema và replication trên server.
D. Giới hạn quyền search/read trong subtree cần thiết.
Đáp án đúng: D

Câu 25. Muốn tạo LDAP entry mới bằng `LdapTemplate`, thao tác nào thường dùng?
A. Dùng `unbind` với DN mới để lưu entity vào directory.
B. Dùng `bind` với DN và các attributes hợp lệ.
C. Dùng `lookup` với DN mới rồi thêm attribute vào kết quả.
D. Dùng `search` với DN mới và filter objectClass.
Đáp án đúng: B

Câu 26. Muốn sửa một attribute trên entry đã tồn tại mà giữ các attribute khác, nên làm gì?
A. Dùng `modifyAttributes` với thay đổi attribute phù hợp.
B. Dùng `unbind` rồi bind lại mỗi khi đổi một thuộc tính.
C. Dùng `rename` từ DN cũ sang DN cũ để cập nhật attribute.
D. Dùng `lookup` và coi việc sửa object Java tự ghi lên LDAP.
Đáp án đúng: A

Câu 27. Khi cần đổi RDN `uid=mai` thành `uid=maianh`, thao tác LDAP nào phù hợp?
A. Chỉ đổi `spring.ldap.base` của ứng dụng sau khi save.
B. Thay filter của repository mà giữ nguyên DN entry.
C. Đổi tên entry bằng operation rename/modify DN.
D. Thực hiện search với filter uid mới rồi ghi kết quả.
Đáp án đúng: C

Câu 28. Muốn xóa một entry có nhiều entry con, điều gì phải cân nhắc?
A. Delete entry cha sẽ xóa cây con theo mặc định LDAP.
B. Delete entry cha thường không được khi vẫn còn entry con.
C. Xóa entry cha sẽ tự move con lên parent kế tiếp.
D. Delete entry cha chỉ yêu cầu chỉnh sửa thuộc tính RDN.
Đáp án đúng: B

Câu 29. Khi search trả nhiều entry, kỹ thuật nào giúp kiểm soát lượng dữ liệu nhận?
A. Tăng số thuộc tính trả về để ít request hơn.
B. Giảm LDAP search base bằng cách đưa DN thành một filter.
C. Đọc toàn bộ entry rồi phân trang trên HTTP controller.
D. Dùng server-side paging control nếu directory hỗ trợ.
Đáp án đúng: D

Câu 30. Để truy vấn LDAP nhanh và giảm tải directory, điều gì quan trọng?
A. Chọn size limit rất lớn và trả mọi field trong directory.
B. Chọn filter wildcard đầu chuỗi cho mọi thuộc tính người dùng.
C. Chọn search base/scope hẹp và filter trên attribute có index.
D. Chọn subtree search toàn cây rồi filter sau ở Java service.
Đáp án đúng: C

Câu 31. Nhiều LDAP entry phải cập nhật trong một quy trình; điều nào nên lưu ý?
A. Mọi lệnh bind và modify được commit nguyên tử theo `@Transactional`.
B. LDAP query filter tự rollback các entry khác nếu một update lỗi.
C. Không mặc định có ACID transaction xuyên nhiều entry như RDBMS.
D. Spring Data LDAP repository tự tạo distributed transaction.
Đáp án đúng: C

Câu 32. Khi kiểm thử mapping `@Entry` và CRUD thực tế, hướng nào đáng tin cậy?
A. Kiểm tra annotation và reflection mà không khởi động LDAP.
B. Chạy LDAP server kiểm thử và assert bind/search/modify bằng schema.
C. Dùng SQL database với bảng mô phỏng DN và objectClass.
D. Mock repository cùng mapper mà không chạy LDAP server thật.
Đáp án đúng: B
