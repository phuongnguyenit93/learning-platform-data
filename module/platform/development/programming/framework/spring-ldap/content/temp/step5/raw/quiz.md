Câu 1. Trong LDAP, Distinguished Name (DN) dùng để biểu diễn điều gì?
A. Tên ngắn được dùng làm một relative component của entry
B. Tên thuộc tính dùng để chỉ objectClass của entry
C. Giá trị của một thuộc tính tìm kiếm trong directory
D. Vị trí định danh một entry trong cây thư mục LDAP
Đáp án đúng: D

Câu 2. RDN trong DN uid=alice,ou=People,dc=example,dc=org là thành phần nào?
A. dc=org định danh entry tương đối với node cha
B. ou=People là RDN của chính entry alice ở bên dưới
C. uid=alice xác định entry tương đối với node cha
D. dc=example là RDN của user alice trong nhánh People
Đáp án đúng: C

Câu 3. Nếu user bob nằm trong ou=People,dc=example,dc=org, DN đầy đủ nào hợp lệ?
A. ou=People,uid=bob,dc=example,dc=org
B. uid=bob,dc=org,ou=People,dc=example
C. dc=example,dc=org,ou=People,uid=bob
D. uid=bob,ou=People,dc=example,dc=org
Đáp án đúng: D

Câu 4. Nếu LdapContextSource có base=dc=example,dc=org, DN tương đối ou=People đại diện cho đâu?
A. Một root entry độc lập với dc=example,dc=org
B. Nhánh ou=People dưới dc=example,dc=org
C. Một DN đủ điều kiện được server gắn với dc=net
D. Một entry thuộc nhánh dc=org nhưng không có base
Đáp án đúng: B

Câu 5. Khi tạo DN chứa tên người dùng nhập từ form, cách nào an toàn hơn nối chuỗi?
A. Dùng LdapNameBuilder để escape và ghép RDN hợp lệ
B. Đưa nguyên chuỗi user nhập sau dấu phẩy của base DN
C. Escape ký tự theo LDAP filter rồi dùng làm DN đầy đủ
D. Loại mọi dấu phẩy trong tên trước khi tạo DN mới
Đáp án đúng: A

Câu 6. Thuộc tính objectClass của LDAP entry có vai trò chính gì?
A. Báo entry là một subentry nên bỏ qua kiểm tra schema
B. Định nghĩa search base mặc định cho toàn bộ LDAP tree
C. Chỉ định authentication method dùng để bind tài khoản
D. Khai các lớp schema quyết định nhóm thuộc tính hợp lệ
Đáp án đúng: D

Câu 7. Khi objectClass yêu cầu attribute MUST theo schema, điều gì nên được bảo đảm?
A. Entry được tạo có giá trị attribute bắt buộc đó
B. Attribute MUST có thể vắng mặt nếu entry có uid
C. Mỗi attribute MUST chỉ được lưu giá trị kiểu boolean
D. Entry chỉ cần khai objectClass và không có attributes
Đáp án đúng: A

Câu 8. Với thuộc tính LDAP nhiều giá trị như member, cần xử lý thế nào?
A. Ép attribute member thành chuỗi chứa dấu phẩy ở giữa
B. Đọc và cập nhật tập giá trị thay vì giả định một chuỗi
C. Chỉ giữ giá trị đầu vì LDAP không lưu collection
D. Ghi nhiều entry riêng cho cùng một thuộc tính member
Đáp án đúng: B

Câu 9. Filter LDAP (uid=alice) biểu diễn điều kiện nào?
A. Thuộc tính uid bắt đầu bằng alice và còn hậu tố
B. Thuộc tính uid bằng giá trị alice trong phạm vi tìm kiếm
C. Tìm entry có DN dạng uid=alice và bỏ qua search base
D. Khớp mọi thuộc tính có giá trị chuỗi alice
Đáp án đúng: B

Câu 10. Filter LDAP (&(objectClass=person)(uid=alice)) kết hợp điều kiện thế nào?
A. Chỉ chọn entry thỏa cả objectClass và uid
B. Chọn entry thỏa một trong hai điều kiện đã nêu
C. Phủ định một trong hai điều kiện để loại guest
D. Kiểm tra objectClass và uid bằng phép so sánh >=
Đáp án đúng: A

Câu 11. Filter LDAP dùng toán tử OR cho uid=alice và uid=bob sẽ chọn entry nào?
A. Entry đồng thời có hai uid là alice và bob
B. Entry không có uid alice và cũng không có uid bob
C. Entry có uid bắt đầu bằng các tiền tố alice và bob
D. Entry có uid bằng alice hoặc uid bằng bob
Đáp án đúng: D

Câu 12. Trong filter LDAP (!(uid=guest)), toán tử ! có tác dụng gì?
A. Chuyển filter thành tìm kiếm chỉ một cấp dưới base
B. Chỉ chọn entry không khai báo bất kỳ objectClass nào
C. Phủ định điều kiện equality uid=guest bên trong
D. Buộc server thực thi matching rule phân biệt hoa thường
Đáp án đúng: C

Câu 13. Filter (cn=An*) thường được dùng để khớp trường hợp nào?
A. Giá trị cn phải bằng chính xác hai ký tự An
B. cn khớp tiền tố An theo phép so sánh substring
C. Giá trị cn có dấu sao thật và không dùng wildcard
D. Giá trị cn chứa An ở bất kỳ vị trí nào trong chuỗi
Đáp án đúng: B

Câu 14. Khi giá trị filter equality chứa ký tự * hoặc (, xử lý nào cần thiết?
A. Chỉ thực hiện URL encode trên kết nối LDAP socket
B. Dùng DN escaping cho cả filter mà không phân biệt
C. Escape ký tự đặc biệt theo quy tắc LDAP filter
D. Loại dấu ngoặc của toàn filter rồi gửi tới server
Đáp án đúng: C

Câu 15. Muốn kết hợp điều kiện equality bằng phép AND trong Spring LDAP, dùng gì?
A. AndFilter kết hợp các filter như EqualsFilter
B. OrFilter kết hợp điều kiện theo phép giao logic
C. LdapNameBuilder ghép filter thành các RDN liên tiếp
D. NotFilter thay thế AND bằng một phép phủ định
Đáp án đúng: A

Câu 16. SearchControls.OBJECT_SCOPE thường giới hạn tìm kiếm như thế nào?
A. Chỉ kiểm tra chính entry tại base DN được chọn
B. Chỉ tìm các entry con trực tiếp mà không gồm base
C. Tìm toàn bộ entry con ở các cấp sâu hơn base
D. Tìm các entry khác naming context có cùng RDN
Đáp án đúng: A

Câu 17. SearchControls.ONELEVEL_SCOPE trên base ou=People sẽ tìm ở đâu?
A. Ở chính base và tất cả các cấp cháu trong nhánh
B. Ở mọi nhánh có RDN bằng People trong directory
C. Chỉ ở chính entry ou=People và không tìm con
D. Trong các entry con trực tiếp của ou=People
Đáp án đúng: D

Câu 18. Khi cần tìm user nằm nhiều cấp dưới base DN, scope nào thường phù hợp?
A. SUBTREE_SCOPE duyệt base và các cấp con của nó
B. OBJECT_SCOPE tìm toàn bộ entry dưới base DN
C. ONELEVEL_SCOPE tìm cả cháu sâu nhiều cấp của base
D. ONELEVEL_SCOPE tìm cả base nhưng không tìm con
Đáp án đúng: A

Câu 19. Nếu LDAP search chậm trên directory lớn, hướng tối ưu nào phù hợp?
A. Chỉ tăng pool size mà giữ nguyên base và filter
B. Giới hạn search base và xem index của attribute lọc
C. Chuyển mọi search thành OBJECT_SCOPE bất kể cấu trúc
D. Bật recursive search vô hạn thay cho chọn search scope
Đáp án đúng: B

Câu 20. Với Spring LDAP, LdapQueryBuilder hỗ trợ việc gì?
A. Thực thi bind với mật khẩu user từ toàn bộ LdapQuery
B. Tạo LdapQuery gồm base, scope và điều kiện filter
C. Chỉ dùng để ánh xạ Attributes thành Java object
D. Mở kết nối TLS trước khi dựng một LDAP filter
Đáp án đúng: B

Câu 21. LdapTemplate.search thường phục vụ tác vụ nào?
A. Tra một entry theo DN cụ thể mà không cần filter tìm kiếm
B. Thay một attribute của entry theo DN đã biết
C. Tạo entry mới từ DN và tập attributes được truyền
D. Search entry bằng base/filter rồi map sang object
Đáp án đúng: D

Câu 22. AttributesMapper trong Spring LDAP thường nhận dữ liệu nào để map entry?
A. DirContextOperations chứa entry cùng DN và mọi thay đổi
B. LdapQuery gồm base, scope, filter của lần tìm kiếm
C. Attributes của entry LDAP được mapper chuyển đổi
D. ContextSource chứa URL và thông tin bind tới server
Đáp án đúng: C

Câu 23. So với AttributesMapper, ContextMapper hữu ích khi cần thông tin nào?
A. ContextMapper truy cập DN qua DirContextOperations
B. Chỉ dữ liệu Attributes mà không có tên entry tương ứng
C. LdapQuery gồm search scope và filter chưa thực thi
D. Cấu hình password và TLS của LdapContextSource
Đáp án đúng: A

Câu 24. Khi biết DN cụ thể của một entry, LdapTemplate.lookup dùng để làm gì?
A. Tìm các entry khớp equality filter trên toàn subtree
B. Đọc entry theo DN mà không cần filter tìm nhiều entry
C. Cập nhật attribute của entry sau khi search hoàn tất
D. Thêm entry theo objectClass rồi trả một DN mới
Đáp án đúng: B

Câu 25. LdapTemplate.bind thường được dùng trong tình huống nào?
A. Tạo entry mới tại DN với các attribute phù hợp
B. Kiểm chứng mật khẩu của user bằng simple authentication
C. Tra cứu entry đang tồn tại và ánh xạ thành Java bean
D. Thay một attribute đơn lẻ của entry theo DN cũ
Đáp án đúng: A

Câu 26. Khi cần sửa riêng thuộc tính mail của entry, API nào phù hợp?
A. LdapTemplate.search sẽ cập nhật mail khi map kết quả
B. LdapTemplate.unbind rồi tự khôi phục entry như ban đầu
C. LdapTemplate.modifyAttributes cập nhật thuộc tính mail
D. LdapTemplate.lookup tự ghi mọi field nhận vào server
Đáp án đúng: C

Câu 27. LdapTemplate.unbind với DN của một leaf entry thường thực hiện gì?
A. Xóa entry tại DN được chỉ định khỏi directory
B. Đóng phiên LDAP user bind và giữ nguyên entry
C. Loại attribute objectClass nhưng không xóa entry
D. Đóng TLS session của ContextSource rồi trả entry
Đáp án đúng: A

Câu 28. DirContextAdapter thường giúp code Spring LDAP thao tác gì?
A. Cấp JDBC transaction cho từng lần LDAP bind
B. Chuyển mọi AttributesMapper thành LDAP filter
C. Tạo schema objectClass mới khi ứng dụng khởi động
D. Đọc, sửa attributes và theo dõi thay đổi của entry
Đáp án đúng: D

Câu 29. Trong Spring LDAP ODM, @Entry dùng với class nhằm mục đích gì?
A. Ánh xạ class domain thành loại LDAP entry tương ứng
B. Đánh dấu attribute phải được coi là RDN của entry
C. Chỉ định password để dùng cho service account bind
D. Giới hạn search scope thành OBJECT_SCOPE cho class
Đáp án đúng: A

Câu 30. Annotation ODM @Id trên đối tượng LDAP thường ánh xạ tới thông tin nào?
A. DN định danh entry trong thư mục
B. Tên attribute dùng làm giá trị cn
C. ObjectClass quyết định cấu trúc entry
D. Một giá trị timestamp khi context refresh
Đáp án đúng: A

Câu 31. Với Spring LDAP ODM, @Attribute(name="cn") dùng để làm gì?
A. Dùng field Java làm DN mới mà không cần RDN
B. Đăng ký objectClass mới có tên cn tại server
C. Ánh xạ LDAP cn vào Java field bằng @Attribute
D. Thiết lập search scope cho mọi truy vấn lấy cn
Đáp án đúng: C

Câu 32. Trong ODM Spring LDAP, @DnAttribute hữu ích ở điểm nào?
A. Ánh xạ từng group member theo giá trị search filter
B. @DnAttribute ánh xạ property vào thành phần RDN
C. Dùng một field làm bind password của LDAP context
D. Thay @Entry để cấu hình search base và scope
Đáp án đúng: B

Câu 33. Khi muốn API truy vấn LDAP theo phong cách fluent, nên cân nhắc gì?
A. LdapClient chỉ hỗ trợ entry creation chứ không tìm kiếm
B. LdapClient cung cấp API fluent cho search LDAP
C. LdapClient đổi toàn bộ LDAP search thành SQL query
D. LdapClient chỉ dùng để đăng ký custom objectClass
Đáp án đúng: B

Câu 34. ContextSource trong Spring LDAP cung cấp vai trò nào cho LdapTemplate?
A. Cấp context để truy cập directory bằng cấu hình kết nối
B. Giữ toàn bộ search result trong cache qua mỗi request
C. Định nghĩa schema objectClass và tạo attribute mặc định
D. Lưu trạng thái phân trang search của user vào database
Đáp án đúng: A

Câu 35. Trong LdapContextSource, nhóm cấu hình nào quan trọng để kết nối?
A. Filter search, mapping attribute và schema của Java class
B. SearchControls scope, count limit và objectClass bắt buộc
C. URL LDAP, base DN và thông tin bind cần thiết
D. Result mapper, query page size và group membership
Đáp án đúng: C

Câu 36. Khi cần tìm user bằng tài khoản service rồi bind kiểm chứng mật khẩu user, phân tách nào đúng?
A. Service bind thành công chứng minh cả mật khẩu user cũng đúng
B. Lấy thuộc tính userPassword rồi đối chiếu plain text mặc định
C. Đăng nhập service là đủ thay cho user bind khi xác thực
D. Service account có quyền tìm; bind user kiểm tra credential riêng
Đáp án đúng: D

Câu 37. Nếu dùng LdapTemplate.authenticate với filter và mật khẩu user, mục tiêu là gì?
A. Tự đồng bộ các group user sang bảng roles của ứng dụng
B. Kiểm tra thông tin đăng nhập bằng xác thực với LDAP directory
C. Thêm thuộc tính objectClass mới cho người dùng vừa bind
D. Đổi bind password của service account sang password user
Đáp án đúng: B

Câu 38. Khi ứng dụng phân quyền dựa vào nhóm LDAP, điều gì cần xem xét?
A. Bind user thành công tự cấp mọi quyền của group quản trị
B. Dùng OU của user thay hoàn toàn cho group membership
C. Kiểm tra membership/group mapping theo schema đang dùng
D. Dùng DN service account làm role mặc định của mọi user
Đáp án đúng: C

Câu 39. Khi cấu hình URL ldaps:// cho kết nối LDAP, kỳ vọng phù hợp là gì?
A. Mở kết nối LDAP plaintext đến lúc application gọi StartTLS
B. Chỉ mã hóa request bind còn LDAP search gửi plaintext
C. Dùng kết nối LDAP được bảo vệ bằng TLS ngay khi kết nối
D. Kết nối tự bỏ qua xác minh TLS certificate phía client
Đáp án đúng: C

Câu 40. StartTLS trong kết nối LDAP thường có vai trò nào?
A. Thêm TLS vào tên DN của entry trước khi chạy search
B. Nâng cấp kết nối LDAP đang mở lên TLS khi được thương lượng
C. Chỉ dùng certificate để thay thế mọi LDAP bind request
D. Đổi ldap:// thành ldaps:// bằng cách thay server port
Đáp án đúng: B

Câu 41. Vì sao khi dùng LDAP qua TLS cần kiểm tra certificate và hostname?
A. Để thay thế mọi thao tác xác thực LDAP user sau khi TLS
B. Để tự xác định vai trò group admin của user hiện tại
C. Để tự nâng cấp search filter thành subtree không giới hạn
D. Để xác minh đúng server và giảm nguy cơ giả mạo kết nối
Đáp án đúng: D

Câu 42. Khi lưu bind password của tài khoản service LDAP, cách nào nên ưu tiên?
A. Ghi password vào URL kết nối LDAP trong file source
B. Lưu bind password trong secret store, tránh hardcode
C. Ghi password trong log DEBUG của ContextSource khi bind
D. Đặt password trong DN rồi dùng làm một RDN của user
Đáp án đúng: B

Câu 43. Connection pooling trong Spring LDAP hữu ích chủ yếu cho việc gì?
A. Cache tất cả search result của user xuyên suốt phiên bind
B. Bật chế độ secure connection mà không cần TLS server
C. Tái sử dụng LDAP context/connection theo cấu hình phù hợp
D. Tạo thêm một LDAP replica khi connection bị chậm
Đáp án đúng: C

Câu 44. Vì sao khi pooling LDAP cần xử lý context lỗi hoặc đã mất kết nối?
A. Context trong pool luôn hợp lệ cho tới khi ứng dụng đóng
B. Query timeout thay thế được kiểm tra connection thực tế
C. Pooling sẽ tự cấp quyền truy cập LDAP khi user mất session
D. Kiểm tra context cũ trước khi tái sử dụng từ pool
Đáp án đúng: D

Câu 45. Khi kết quả LDAP search lớn và server hỗ trợ paged results, công cụ nào hữu ích?
A. LdapTemplate.unbind tự chia search result thành nhiều trang
B. LdapQueryBuilder tự chạy toàn bộ trang chỉ qua base DN
C. AttributesMapper lưu page cookie trong mọi LDAP entry
D. PagedResultsDirContextProcessor quản lý cookie phân trang
Đáp án đúng: D

Câu 46. Khi LDAP server trả lỗi tìm kiếm hoặc naming, tầng Spring LDAP hỗ trợ gì?
A. Tự tạo entry rỗng rồi trả về như lookup thành công
B. Đổi lỗi bind thành boolean true nếu đã kết nối TLS
C. Chuyển NamingException thành exception Spring LDAP
D. Ghi toàn bộ search exception vào server audit log
Đáp án đúng: C

Câu 47. Để kiểm thử LDAP search, filter escaping và bind mà không dùng directory production, nên làm gì?
A. Chỉ mock LdapTemplate rồi coi TLS server đã được kiểm thử
B. Chỉ assert URL trong LdapContextSource mà bỏ kết nối
C. Test tích hợp với LDAP server thử và dữ liệu kiểm soát
D. Kiểm tra một LDAP filter có giá trị cố định, bỏ input lạ
Đáp án đúng: C

Câu 48. Khi bind service thành công nhưng modifyAttributes bị từ chối, nguyên nhân nào hợp lý?
A. LdapTemplate.search tự tắt mọi quyền ghi của bind user
B. LDAP equality filter không cho phép modify một attribute
C. DN của user tự trở thành read-only sau khi lookup
D. LDAP access control chưa cấp quyền ghi lên entry đích
Đáp án đúng: D
