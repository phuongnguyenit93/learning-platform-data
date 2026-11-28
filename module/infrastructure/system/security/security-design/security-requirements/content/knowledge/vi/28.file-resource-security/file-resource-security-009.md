# Path traversal defense

## 1. Path traversal là gì?

**Path traversal** là việc đầu vào ảnh hưởng tới cách hệ thống định vị tài nguyên, khiến thao tác đọc, ghi, xóa hoặc xử lý đi ra ngoài phạm vi được phép. Đầu vào đó có thể là đường dẫn, tên tệp, tên entry trong archive, khóa tài nguyên hoặc tham chiếu được lấy từ dữ liệu đã lưu trước đó.

Ví dụ, một dịch vụ tải báo cáo lấy giá trị client gửi rồi ghép vào thư mục của tenant. Nếu tên có thành phần đi lên thư mục cha và hệ thống lưu trữ diễn giải nó, thao tác có thể chạm tới tài liệu của tenant khác hoặc tệp cấu hình của dịch vụ.

Trong chương **File và resource security** của module yêu cầu bảo mật, mục tiêu là chuyển rủi ro đó thành các yêu cầu cụ thể về danh tính tài nguyên, quyền thao tác, giới hạn phân giải và bằng chứng kiểm thử. Chỉ yêu cầu “lọc chuỗi nguy hiểm” không xác định đủ ranh giới cần bảo vệ.

Hai câu hỏi phải được trả lời đồng thời:

1. **Chủ thể có quyền thực hiện hành động trên tài nguyên này không?**
2. **Cơ chế định vị có bảo đảm thao tác thực tế chỉ chạm tới đúng tài nguyên được phép không?**

Một đường dẫn nằm trong thư mục dùng chung không có nghĩa mọi tenant được đọc nó. Ngược lại, kiểm tra quyền trong cơ sở dữ liệu cũng chưa đủ nếu một tham chiếu lưu trữ bị phân giải sang đối tượng khác.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Nhận diện đầu vào và đường đi có thể ảnh hưởng tới thao tác tài nguyên.
- Đặc tả quyền theo tenant, đối tượng và hành động thay vì dựa vào tên khó đoán.
- Phân biệt chuẩn hóa cú pháp, phân giải thực tế và cưỡng chế tại điểm I/O.
- Viết yêu cầu cho liên kết, TOCTOU, tạo độc quyền, xóa và giải nén.
- Xây dựng tiêu chí nghiệm thu cho đường vào trực tiếp, dữ liệu gián tiếp và khác biệt nền tảng.

## 2. Tài sản, điểm vào và ranh giới tin cậy

### 2.1. Không chỉ có endpoint download

Các điểm vào cần được đưa vào mô hình đe dọa gồm:

| Điểm vào | Đầu vào có ảnh hưởng | Tác động cần xem xét |
|---|---|---|
| Download và preview | ID, tên hoặc tham chiếu tệp | Đọc bí mật, đọc tệp tenant khác |
| Upload và thay tệp | Tên gốc, khóa đích, thư mục | Ghi đè dữ liệu hoặc đặt nội dung ở nơi không được phép |
| Export và tạo báo cáo | Tên đầu ra, mẫu báo cáo, vùng tạm | Ghi ngoài phạm vi hoặc đọc mẫu tùy ý |
| Import archive | Tên entry, kiểu entry, liên kết | Ghi ra ngoài thư mục giải nén |
| Xóa và dọn dữ liệu | ID hoặc tham chiếu từ metadata, job | Xóa nhầm tài nguyên, thư mục cha hoặc phiên bản khác |
| Xử lý nền | Tham chiếu được lưu từ request trước | Tạo tác động sau khi đầu vào đã rời khỏi endpoint |
| Tài nguyên tĩnh hoặc template | Tên tài nguyên theo cấu hình hoặc tham số | Đọc cấu hình, mã nguồn hoặc dữ liệu không được công bố |

Đầu vào lấy từ cơ sở dữ liệu, hàng đợi hoặc manifest chưa chắc đáng tin. Nếu trước đó người dùng có thể đưa một đường dẫn vào trường metadata, worker sử dụng trường đó vẫn phải thực thi ranh giới truy cập.

### 2.2. Xác định phạm vi được phép

Cần chốt các yếu tố sau:

- Chủ thể và tenant được xác minh bằng nguồn nào.
- Những loại tài nguyên và hành động nào được hỗ trợ.
- Root lưu trữ nào thuộc quyền quản lý của dịch vụ.
- Ai có thể tạo, đổi tên hoặc sửa các thành phần bên trong và phía trên root.
- Có cho đi qua liên kết, junction, mount point hoặc vùng lưu trữ khác không.
- Các tiến trình khác, công cụ quản trị và tác vụ nền có cùng thực thi chính sách không.

Mô hình “người dùng chỉ gửi request HTTP” khác với mô hình có một bên không tin cậy được quyền ghi trực tiếp vào một phần cây thư mục. Khi có khả năng thay cấu trúc thư mục, thiết kế cần xem xét cả việc thay đối tượng giữa kiểm tra và sử dụng.

### 2.3. Bất biến cần giữ

Một bất biến khái quát:

> Mỗi thao tác tài nguyên phải được thực hiện trên đúng đối tượng và phiên bản đã được cho phép, trong namespace và phạm vi lưu trữ được phê duyệt, với đúng loại thao tác. Đầu vào không tin cậy không được mở rộng phạm vi đó qua cú pháp, cách phân giải hoặc thay đổi đồng thời.

Namespace ở đây là không gian định danh mà cơ chế lưu trữ sử dụng. Nó có thể là cây thư mục, một vùng object storage hoặc một dịch vụ tài nguyên. Phải xác định cụ thể thay vì giả định mọi cơ chế đều có cùng ngữ nghĩa đường dẫn.

## 3. Ưu tiên hợp đồng tài nguyên thay cho đường dẫn tùy ý

### 3.1. Client gửi ID, máy chủ ánh xạ tới storage

Một hợp đồng download minh họa chỉ nhận `file_id`. Máy chủ lấy danh tính và tenant từ cơ chế xác thực, kiểm tra quyền trên bản ghi tệp, rồi ánh xạ bản ghi đó sang tham chiếu lưu trữ do máy chủ quản lý.

```text
Danh tính đã xác minh + file_id + hành động
                 ↓
Kiểm tra quyền đối tượng và trạng thái
                 ↓
Tham chiếu storage thuộc tenant và phiên bản được phép
                 ↓
Thao tác I/O bị ràng buộc trong phạm vi đã cấu hình
```

Trong một ví dụ, `file_id` có thể là 32 ký tự hex chữ thường, được máy chủ cấp. Kiểm tra grammar này giúp endpoint không nhận đường dẫn tùy ý, nhưng không thay thế quyền đối tượng. Người biết ID của tệp khác vẫn không có quyền đọc nó.

Tenant dùng để chọn vùng lưu trữ phải đến từ danh tính và quan hệ đối tượng đã được xác minh. Không để một header hoặc tham số tự khai chọn root của tenant khác.

### 3.2. Tên hiển thị không phải địa chỉ I/O

Tên gốc có thể được giữ làm metadata nếu nghiệp vụ cần. Nó phải được giới hạn, hiển thị và ghi log theo chính sách dữ liệu, nhưng không được tự trở thành đường dẫn, tên chương trình hay khóa ghi đè.

Ví dụ, báo cáo có tên hiển thị “Báo cáo tháng 11.pdf”, trong khi tham chiếu lưu trữ được tạo từ định danh tenant nội bộ, ID tệp và phiên bản do máy chủ cấp. Đổi tên hiển thị không làm thay đổi nơi đọc byte.

Mọi thành phần dùng để dựng tham chiếu nội bộ cần có nguồn và grammar xác định. Việc thay đường dẫn đầy đủ bằng một “tên ngắn” vẫn không giúp nếu tên đó tiếp tục chứa cú pháp được hệ thống lưu trữ diễn giải.

### 3.3. Root và chế độ thao tác là cấu hình có thẩm quyền

Root đọc, root tạm, root đầu ra và root import cần được cấu hình rõ, có quyền hệ điều hành phù hợp. Request không được tự chọn root, chế độ mở hoặc quyền ghi.

Nếu cấu hình thiếu hoặc không hợp lệ, hệ thống không được tự rơi về thư mục hiện tại, thư mục cha hoặc một đường dẫn mặc định rộng hơn. Lỗi cấu hình phải có trạng thái rõ và không mở rộng quyền truy cập.

## 4. Chuẩn hóa đầu vào và ngữ nghĩa nền tảng

### 4.1. Phải biết chuỗi nào thực sự tới điểm I/O

Dữ liệu có thể đi qua bộ định tuyến, URL decoder, framework, bộ chuẩn hóa Unicode, xử lý dấu phân cách và API lưu trữ. Nếu các tầng hiểu khác nhau, một chuỗi tưởng như vô hại ở tầng kiểm tra có thể trở thành đường dẫn khác ở tầng sử dụng.

Yêu cầu cần quy định nơi giải mã, số lần giải mã và dạng dữ liệu được chuyển sang bước tiếp theo. Không kiểm tra một dạng rồi cho tầng sau giải mã tiếp thành cú pháp có ý nghĩa mới.

Trong hợp đồng chỉ nhận ID, các ký tự ngoài grammar cần bị từ chối sau bước giải mã giao thức đã định. Không cố sửa một đầu vào không hợp lệ bằng cách xóa vài đoạn rồi tiếp tục dùng nó làm đường dẫn.

Nếu một API cũ bắt buộc nhận đường dẫn tương đối, phải có đặc tả riêng về grammar thành phần, độ dài, dấu phân cách, ký tự điều khiển, mã hóa và cách xử lý lỗi. Không coi nó tương đương với API chỉ nhận ID.

### 4.2. Những dạng đường dẫn cần đưa vào phân tích

| Dạng | Lý do cần chú ý |
|---|---|
| Thành phần thư mục cha như `..` | Có thể đi lên ngoài thư mục được ghép |
| Đường dẫn tuyệt đối | Có thể làm thao tác bỏ qua root mà ứng dụng dự định dùng |
| Dấu phân cách khác hoặc kết hợp | Các tầng và nền tảng có thể diễn giải khác nhau |
| Đường dẫn gắn ổ đĩa hoặc phụ thuộc thư mục làm việc của ổ | Không nhất thiết là đường dẫn tương đối theo root ứng dụng |
| UNC hoặc tên tài nguyên mạng | Có thể chuyển thao tác sang namespace khác và phát sinh truy cập mạng |
| Namespace thiết bị hoặc dạng đường dẫn đặc biệt | Có thể vượt giả định rằng đích là một tệp thông thường |
| Tên có ngữ nghĩa đặc biệt, stream hoặc alias | Chuỗi tên không nhất thiết ánh xạ đơn giản tới một tệp thông thường |
| Tên khác nhau nhưng bị coi tương đương | Có thể gây va chạm hoặc vượt kiểm tra theo tên |

Trên môi trường Windows, cần phân biệt các dạng như đường dẫn có ổ đĩa, đường dẫn tương đối theo ổ, UNC, namespace đặc biệt và alternate data stream nếu cơ chế liên quan hỗ trợ. Trên môi trường khác, cũng phải xác định dấu phân cách, liên kết và namespace thực tế.

Không suy ra hành vi chỉ từ tên hệ điều hành. Phân biệt hoa thường, alias, chuẩn hóa tên và giới hạn còn phụ thuộc filesystem, cấu hình thư mục hoặc backend. Các dạng không thuộc hợp đồng nên bị loại thay vì được tự động chuyển sang một namespace mới.

### 4.3. So sánh prefix chuỗi không chứng minh containment

Giả sử root là:

```text
/srv/app-data/tenant-A
```

Đường dẫn sau có cùng prefix ký tự nhưng không nằm trong root đó:

```text
/srv/app-data/tenant-A-backup/report.pdf
```

So sánh cần hiểu ranh giới thành phần và ngữ nghĩa của backend. Tương tự, phải xử lý đúng dấu phân cách, phân biệt hoa thường và dạng tên được nền tảng coi tương đương.

Ngay cả một phép so sánh containment đúng trên chuỗi đã chuẩn hóa cũng chưa giải quyết liên kết hoặc việc cây thư mục thay đổi trước thao tác I/O. Đây là một lớp kiểm tra, không phải toàn bộ cơ chế cưỡng chế.

## 5. Canonicalization và giới hạn của kiểm tra đường dẫn

### 5.1. Phân biệt các bước

| Bước | Mục đích | Điều chưa tự bảo đảm |
|---|---|---|
| Giải mã giao thức | Lấy giá trị theo hợp đồng đầu vào | Không chứng minh đường dẫn được phép |
| Chuẩn hóa cú pháp | Xử lý thành phần theo quy tắc được chọn | Không nhất thiết phân giải liên kết hoặc đối tượng thực |
| Canonicalization theo backend | Xác định dạng hoặc đích theo ngữ nghĩa lưu trữ | Đích có thể đổi trước bước mở nếu thiếu liên kết nhất quán |
| Kiểm tra containment | Đối chiếu với root và namespace được phép | Không thay thế quyền đối tượng |
| Thao tác I/O bị ràng buộc | Cưỡng chế phạm vi trên đối tượng thực | Vẫn cần đúng quyền, loại tài nguyên và vòng đời dữ liệu |

Thuật ngữ canonicalization có thể được các thư viện dùng với bảo đảm khác nhau. Cần kiểm tra hợp đồng của cơ chế đã chọn thay vì suy rằng tên hàm có chữ “canonical” là đủ.

### 5.2. Trường hợp tạo mới

Tệp cần tạo có thể chưa tồn tại nên không thể giả định một hàm phân giải tệp hiện hữu sẽ trả kết quả đầy đủ. Cần bảo vệ thư mục cha thực, tên đối tượng mới và việc tạo độc quyền trong phạm vi đó.

Kiểm tra “đích chưa tồn tại” rồi mới tạo có thể bị xen kẽ bởi một thao tác khác. Nếu yêu cầu không ghi đè, phải dùng cơ chế tạo có bảo đảm không mở hoặc ghi đè đối tượng đã tồn tại ngoài hợp đồng, đồng thời bảo vệ quá trình đi qua các thư mục cha.

### 5.3. Không tiếp tục bằng dữ liệu thô khi kiểm tra lỗi

Nếu phân giải, kiểm tra quyền hoặc xác minh loại đối tượng thất bại, ứng dụng không được chuyển sang dùng đường dẫn gốc để “thử lại cho chắc”. Quy trình lỗi phải giữ nguyên hoặc thu hẹp phạm vi quyền.

Thay đổi cấu hình root, di chuyển dữ liệu hoặc hỗ trợ backend mới cần được đánh giá lại theo cùng các điều kiện. Một thuật toán đúng với một namespace không tự đúng với namespace có quy tắc phân giải khác.

## 6. Cưỡng chế tại điểm I/O và xử lý TOCTOU

### 6.1. Kiểm tra đúng nhưng mở sai vẫn là lỗi

Một lịch có thể xảy ra:

```text
T0: Ứng dụng phân giải tên và xác nhận đích nằm trong root.
T1: Một bên có quyền ghi thay thành phần thư mục hoặc liên kết.
T2: Ứng dụng mở lại tên cũ; backend phân giải sang đối tượng khác.
```

Đây là TOCTOU: kết quả kiểm tra tại T0 không còn ràng buộc được đối tượng sử dụng tại T2. Rút ngắn khoảng thời gian không tạo ra bảo đảm rằng không có thao tác xen kẽ.

Cần chọn cơ chế nền tảng có thể giữ ràng buộc với root đã được xác minh, kiểm soát việc đi qua các thành phần và thao tác trên tham chiếu đối tượng đáng tin cậy. Khi có thể, mở một lần rồi sử dụng chính handle hoặc tham chiếu đó thay vì kiểm tra một đường dẫn rồi phân giải lại tên ở bước đọc, ghi hoặc xóa.

### 6.2. Chính sách liên kết phải rõ

Trong mô hình tham chiếu của bài, các thành phần dữ liệu do người dùng hoặc nguồn không tin cậy tạo ra không được chuyển hướng qua symlink, hard link, junction hay cơ chế tương đương để mở rộng phạm vi truy cập. Những điểm gắn lưu trữ được quản trị phê duyệt phải được mô tả trong cấu hình root và mô hình triển khai.

Một kiểm tra chỉ áp dụng cho thành phần cuối chưa chứng minh an toàn nếu thư mục cha cũng có thể là điểm chuyển hướng. Cũng không nên giả định mọi dạng liên kết đều được biểu diễn giống nhau trên các nền tảng.

Quyền ghi vào root, thư mục cha và vùng staging cần được giới hạn để giảm khả năng thay cấu trúc ngoài giao thức của dịch vụ. Nếu bên không tin cậy vẫn có thể sửa cây thư mục, cơ chế I/O phải chịu được mô hình đó hoặc kiến trúc phải thay đổi để loại khả năng này.

Hard link gắn nhiều tên với cùng một đối tượng; nó không nhất thiết là chuỗi chuyển hướng được đi theo khi mở. Vì vậy, chính sách không đi theo symlink không tự phát hiện hoặc loại bỏ mọi hard link. Cần kiểm soát việc tạo liên kết, nguồn đối tượng và danh tính tài nguyên, hoặc dùng cách ly lưu trữ phù hợp với rủi ro. Tương tự, một mount point được nhìn thấy dưới root vẫn cần thuộc mô hình triển khai đã được phê duyệt.

### 6.3. Mô tả trách nhiệm bằng pseudocode

```text
download(request):
    identity = verify_identity(request)
    file_id = require_valid_resource_id(request.file_id)
    resource = authorize_current_resource(identity, file_id, action=READ)

    root_ref = configured_root_for(resource)
    storage_ref = server_owned_storage_reference(resource)

    handle = confined_storage.open_read(
        root_ref,
        storage_ref,
        redirect_policy=REJECT_UNTRUSTED_REDIRECTION,
        object_type=REGULAR_FILE
    )

    require handle matches authorized resource and version
    stream_from_same_handle(handle)
```

Các hàm trên là mô tả trách nhiệm, không phải API chuẩn có sẵn. Khi triển khai, phải chứng minh wrapper và cơ chế nền tảng thật sự cung cấp các bảo đảm đó, bao gồm hành vi với từng thành phần, liên kết và thay đổi đồng thời.

Kiểm tra loại đối tượng cũng quan trọng: endpoint tải tài liệu không nên mở thiết bị, pipe, socket hoặc thư mục chỉ vì tên của chúng vượt được kiểm tra cú pháp. Loại đối tượng được phép phải gắn với chức năng và tài nguyên cụ thể.

### 6.4. Giới hạn quyền của tiến trình

Dịch vụ nên chỉ có quyền cần thiết trên vùng dữ liệu tương ứng. Tách vùng đọc, ghi tạm, đầu ra và dữ liệu cách ly giúp giảm phạm vi hậu quả nếu có lỗi định vị.

Cơ chế cách ly của môi trường có thể bổ sung ranh giới filesystem hoặc namespace cho tiến trình. Tuy nhiên, quyền hệ điều hành hoặc sandbox không thay thế phân quyền nghiệp vụ giữa các tenant nếu cùng một tài khoản dịch vụ vẫn đọc được tất cả dữ liệu của họ.

## 7. Yêu cầu riêng theo loại thao tác

### 7.1. Đọc và preview

Điểm thực thi phải xác minh quyền đọc đúng đối tượng, phiên bản và trạng thái được phục vụ. Mọi đường preview, thumbnail, export hàng loạt và truy vấn metadata nhạy cảm cũng thuộc phạm vi.

Không sử dụng tham số đường dẫn do người dùng gửi để truy cập kho cấu hình, mẫu nội bộ hoặc tệp ứng dụng. Nếu nghiệp vụ cho chọn template, nên chọn từ danh mục định danh được phê duyệt và ánh xạ phía máy chủ.

Tham chiếu dạng URI không được tự chuyển sang quyền đọc tài nguyên mạng hoặc tài nguyên cục bộ ngoài hợp đồng. API được thiết kế để đọc tệp của sản phẩm không nên trở thành bộ mở mọi loại địa chỉ mà thư viện bên dưới hỗ trợ.

### 7.2. Tạo và ghi

Khóa lưu trữ, thư mục cha và chế độ tạo phải do máy chủ xác định. Nếu yêu cầu là tạo mới, thao tác phải không ghi đè một đối tượng có trước hoặc đi theo liên kết do bên khác chuẩn bị.

Thư mục được tạo theo yêu cầu nghiệp vụ cũng phải thuộc phạm vi đã cấp quyền. Không tự tạo hàng loạt thư mục theo chuỗi client gửi rồi mới kiểm tra sau khi đã có tác động.

Vùng tạm cần nằm trong namespace do dịch vụ kiểm soát, có tên do máy chủ cấp và quyền phù hợp. Không dùng tên dự đoán được cùng thao tác ghi đè để thay cho cơ chế tạo độc quyền.

### 7.3. Thay thế và đổi tên

Thay thế tệp cần quyền riêng và ngữ nghĩa phiên bản rõ ràng. Cần biết đối tượng cũ nào được phép thay, đối tượng mới được tạo ở đâu và thời điểm tham chiếu chuyển sang phiên bản mới.

Nếu dùng đổi tên hoặc thao tác thay thế nguyên tử của backend, bảo đảm đó chỉ bao phủ phạm vi mà backend cam kết. Nó không tự xác minh quyền tenant, điều kiện phê duyệt hoặc việc cả nguồn và đích đều thuộc namespace được phép.

### 7.4. Xóa và dọn dữ liệu

Tác vụ xóa nên nhận định danh tài nguyên hoặc tham chiếu nội bộ được kiểm soát, không nhận đường dẫn tùy ý từ người dùng. Trước khi xóa, cần xác minh đúng đối tượng và thế hệ hoặc phiên bản để tránh xóa một tài nguyên mới dùng lại tên cũ.

Xóa thư mục đệ quy là quyền và phạm vi khác với xóa một tệp. Nếu có nhu cầu này, phải định nghĩa root công việc, các đối tượng được duyệt, ngân sách và chính sách liên kết. Không cho giá trị rỗng, lỗi ánh xạ hoặc thao tác lấy thư mục cha biến thành lệnh xóa phạm vi rộng hơn.

Tác vụ cleanup cần chạy lại an toàn: không xóa nhầm đối tượng của job khác và không bỏ qua ranh giới chỉ vì dữ liệu đến từ hàng đợi nội bộ.

### 7.5. Liệt kê tài nguyên

Quyền đọc một tài nguyên không tự tạo quyền liệt kê mọi tệp trong cùng vùng. Nếu có chức năng liệt kê, phải giới hạn theo quan hệ nghiệp vụ và tenant, không cung cấp một trình duyệt filesystem tổng quát qua tham số thư mục.

## 8. Archive và thư mục làm việc

### 8.1. Tên entry là đầu vào không tin cậy

Khi giải nén, mỗi entry có thể mang tên, kiểu đối tượng và thuộc tính ảnh hưởng tới nơi ghi. Cần kiểm tra từng entry theo chính sách, đồng thời cưỡng chế phạm vi tại thao tác tạo thực tế.

Chính sách tham chiếu chỉ nhận entry là tệp thông thường hoặc thư mục trong vùng staging riêng của job, không nhận đường dẫn tuyệt đối, thành phần thoát root hay entry liên kết đặc biệt. Các dạng tên có thể bị backend diễn giải khác hoặc gây va chạm phải có hành vi từ chối xác định.

Không giải nén trực tiếp vào thư mục ứng dụng, root dùng chung hoặc nơi chứa tệp của tenant khác. Chỉ sau khi dữ liệu được xác minh và có quyền mới đưa kết quả tới namespace được công bố bằng quy trình có kiểm soát.

### 8.2. Kiểm tra mọi tên trước chưa chắc đủ

Nếu một entry có thể tạo liên kết hoặc thay cấu trúc rồi entry tiếp theo đi qua cấu trúc đó, kiểm tra chuỗi ban đầu có thể không còn đúng lúc ghi. Vì vậy, phải bảo vệ cả kiểu entry, thứ tự thao tác và cách tạo dưới root staging.

Cần xử lý trường hợp hai tên được filesystem coi tương đương, tệp trùng với tên thư mục, entry lặp và biến thể hoa thường theo backend. Không để công cụ tự ghi đè hoặc đổi tên ngoài chính sách rồi vẫn coi kết quả đã được xác minh.

Ví dụ ngân sách cho một tính năng import có thể là tối đa 1.000 entry, độ sâu 8 cấp và tổng 100 MiB byte giải nén thực. Đây là tham số minh họa; cần bổ sung giới hạn mỗi entry, thời gian, bộ nhớ và dung lượng tạm cho sản phẩm thật. Không tin tổng kích thước khai báo trong archive là tổng byte chắc chắn sẽ sinh ra.

### 8.3. Cleanup và archive đầu ra

Nếu giải nén thất bại, chỉ dọn staging thuộc job đó bằng cơ chế đã giữ ranh giới. Không dùng tên entry lỗi để tính lại đường dẫn dọn hoặc lấy thư mục cha quá rộng.

Khi tạo archive đầu ra, tên entry cũng cần là tên ảo thuộc hợp đồng, không mang đường dẫn nội bộ hoặc thành phần có thể làm phía nhận giải nén ra ngoài phạm vi. Việc đọc nguồn an toàn chưa tự chứng minh tên được đưa vào archive an toàn.

## 9. Object storage, URL và cache

### 9.1. Khóa object không nhất thiết là đường dẫn filesystem

Một backend có thể coi dấu phân cách và các thành phần giống đường dẫn là ký tự trong khóa, trong khi ứng dụng, proxy hoặc công cụ đồng bộ lại diễn giải chúng. Cần phân tích toàn bộ chuỗi sử dụng, không kết luận có hoặc không có traversal chỉ dựa vào hình dạng khóa.

Máy chủ cần ánh xạ định danh tài nguyên tới đúng bucket hoặc vùng lưu trữ, tenant, khóa và phiên bản được phép. Client không được tự chọn bucket, prefix đặc quyền hoặc khóa của đối tượng khác.

Nếu có bước đưa object xuống filesystem để xử lý, bước đó phải tuân yêu cầu filesystem như mọi đầu vào khác. Một khóa hợp lệ trong object storage có thể không phải tên hợp lệ hoặc an toàn trên máy xử lý.

### 9.2. URL tạm thời phải cấp đúng phạm vi

Trước khi cấp URL đọc hoặc ghi, cần kiểm tra quyền hiện hành và ánh xạ tới đúng đối tượng, phiên bản, thao tác và thời hạn. Không ký trực tiếp một đường dẫn hoặc khóa client tự chọn mà chưa được cho phép.

URL khó đoán hoặc có chữ ký không sửa được lỗi ánh xạ ban đầu. Nếu máy chủ đã cấp quyền cho sai đối tượng, chữ ký chỉ giúp sử dụng quyền đã cấp sai đó.

Hành vi sau thu hồi quyền, hết hạn hoặc thay phiên bản phải được công bố theo khả năng cơ chế phân phối. Không gọi một URL có thời hạn là thu hồi tức thì nếu nó vẫn được backend chấp nhận trong thời gian còn lại.

### 9.3. Cache giữ nguyên ranh giới quyền

Cache phải phân biệt đầy đủ các yếu tố ảnh hưởng tới quyền đọc và phiên bản. Một kết quả được tạo bằng quyền rộng hơn không được dùng lại cho người có quyền hẹp hơn chỉ vì tham số chuỗi giống nhau.

Kiểm tra các biến thể tên hoặc mã hóa đi qua cache và backend. Nếu cache chọn một tài nguyên còn backend chọn tài nguyên khác, có thể phát sinh lỗi định tuyến hoặc lộ dữ liệu dù từng thành phần có kiểm tra riêng.

## 10. Lỗi, audit và quản trị cấu hình

### 10.1. Lỗi không làm mở rộng phạm vi

Cần có hành vi xác định cho ID sai grammar, đối tượng không được phép, lỗi phân giải, liên kết bị cấm, loại tài nguyên không được hỗ trợ và cấu hình root không hợp lệ.

Phản hồi bên ngoài không nên tiết lộ đường dẫn vật lý, stack trace, thông tin xác thực hoặc sự tồn tại của tài nguyên ngoài quyền. Mã lỗi và payload phải theo chính sách của sản phẩm; chi tiết điều tra được đưa vào kênh có phân quyền.

Không bắt một lỗi kiểm tra rồi thử lại bằng API ít ràng buộc hơn. Không đổi root, bỏ kiểm tra liên kết hoặc dùng chế độ ghi đè chỉ để làm thao tác thành công.

### 10.2. Audit quyết định và tác động

Bằng chứng nên liên kết được danh tính, tenant, hành động, ID tài nguyên, phiên bản, namespace hoặc root logic, quyết định, mã lý do và kết quả thực tế. Đường dẫn vật lý chỉ được ghi khi thực sự cần và kênh lưu có chính sách phù hợp.

Đầu vào bị từ chối có thể chứa dữ liệu nhạy cảm hoặc ký tự điều khiển. Cần giới hạn độ dài và mã hóa khi ghi, hiển thị; không cho log trở thành nơi chèn cấu trúc hoặc làm lộ bí mật. Token và URL cấp quyền không được ghi nguyên vẹn ngoài chính sách.

Số lượng lớn request bị từ chối cần được quan sát bằng bộ đếm và log có ngân sách. Việc lấy mẫu phải được công bố để không coi log mẫu là toàn bộ số lần xảy ra.

### 10.3. Thay root và backend là thay đổi bảo mật

Root, tài khoản dịch vụ, chính sách liên kết và ánh xạ storage phải được sửa bằng quyền quản trị phù hợp, có phiên bản và audit. Cấu hình mới cần được xác minh trước khi nhận tải.

Di chuyển sang filesystem, object storage hoặc công cụ giải nén khác có thể thay đổi ngữ nghĩa tên. Cần chạy lại các kiểm chứng liên quan, kể cả khi định dạng API không thay đổi.

## 11. Bộ yêu cầu bảo mật minh họa

Xét dịch vụ quản lý tài liệu nhiều tenant, có API đọc theo `file_id`, lưu tệp bằng tham chiếu nội bộ và có tính năng import archive riêng. Bộ yêu cầu sau là mẫu để liên kết rủi ro với nơi thực thi và kiểm thử.

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| PT-01 | API tài nguyên chỉ nhận định danh theo grammar được công bố; trong ví dụ, `file_id` gồm đúng 32 ký tự hex chữ thường sau bước giải mã giao thức đã định | ID hợp lệ và các đầu vào ngoài grammar qua mọi tuyến API |
| PT-02 | Tenant, quyền đối tượng, hành động và phiên bản phải được xác minh phía máy chủ; tên hoặc ID khó đoán không tạo quyền | Truy cập chéo tenant, sai hành động và phiên bản không được phép |
| PT-03 | Root, namespace, khóa lưu trữ và chế độ I/O phải đến từ cấu hình hoặc ánh xạ có thẩm quyền; không dùng tên hiển thị để quyết định nơi thao tác | Tên không tin cậy, metadata bị thay trong bài thử và cấu hình lỗi |
| PT-04 | Chuỗi giải mã và chuẩn hóa phải nhất quán; dạng không thuộc hợp đồng không được sửa thành đường dẫn rồi sử dụng; không có bước giải mã sau kiểm tra tạo cú pháp mới | Biến thể mã hóa, dấu phân cách và dữ liệu đi qua nhiều tầng |
| PT-05 | Mọi thao tác I/O phải bị ràng buộc với root và namespace được phép theo ngữ nghĩa backend, giữ đúng đối tượng trước thay đổi đồng thời; prefix chuỗi không được coi là bằng chứng duy nhất | Root gần tên, liên kết và thay thành phần giữa kiểm tra và mở |
| PT-06 | Chính sách liên kết và điểm gắn lưu trữ phải được thực thi trên toàn đường đi liên quan; nguồn không tin cậy không được tạo liên kết làm mở rộng phạm vi | Symlink, hard link, junction hoặc cơ chế nền tảng thuộc mô hình đe dọa |
| PT-07 | Endpoint tài liệu chỉ được thao tác loại đối tượng đã định; trong ví dụ đọc là tệp thông thường | Thư mục và loại đối tượng đặc biệt không được mở để phục vụ |
| PT-08 | Tạo mới phải có bảo đảm không ghi đè; thay thế phải có quyền và phiên bản riêng; source và destination đều phải đúng phạm vi | Tranh chấp tạo cùng đích, thay thế trái quyền và đổi tên |
| PT-09 | Xóa phải gắn với đúng đối tượng và phiên bản; tham chiếu rỗng hoặc lỗi không được mở rộng thành thư mục cha; xóa đệ quy cần quyền và phạm vi riêng | Dữ liệu job cũ, ID lỗi, cleanup chạy lại và marker ngoài phạm vi |
| PT-10 | Import archive phải kiểm tra từng entry và cưỡng chế nơi tạo thực; entry không hợp lệ hoặc va chạm không được ghi ngoài staging hay ghi đè trái chính sách | Tên entry, entry liên kết, entry lặp và thay cấu trúc theo thứ tự |
| PT-11 | URL tạm thời và cache chỉ được cấp hoặc phục vụ đúng tài nguyên, phiên bản và phạm vi quyền; ký một tham chiếu tự khai không được thay thế phân quyền | Khóa khác tenant, cache có quyền rộng hơn và URL cấp sai đối tượng |
| PT-12 | Lỗi không được làm giảm kiểm soát; audit liên kết quyết định với tác động và không tiết lộ bí mật ngoài chính sách | Lỗi root, lỗi phân giải, đường fallback và dữ liệu phản hồi, log |

Nếu sản phẩm buộc phải nhận đường dẫn tương đối, PT-01 cần được thay bằng một hợp đồng đường dẫn cụ thể và kiểm thử tương ứng. Không dùng grammar của ID để tuyên bố đã bảo vệ một endpoint khác vẫn nhận đường dẫn tự do.

Các tham số độ dài, ngân sách import, thời hạn URL, quyền quản trị và lưu audit phải được chốt trong đặc tả triển khai. Chỉ ghi “lọc đầu vào”, “chuẩn hóa an toàn” hoặc “kiểm tra quyền đầy đủ” chưa đủ để nghiệm thu.

## 12. Tiêu chí nghiệm thu và dữ liệu kiểm thử

### 12.1. Chuẩn bị tài nguyên đánh dấu

Trong môi trường kiểm thử được kiểm soát, tạo tài nguyên hợp lệ của tenant A và các tệp đánh dấu có nội dung phân biệt ở tenant B, vùng cấu hình và một thư mục có tên gần giống root A.

Ví dụ tên logic trên một backend filesystem:

```text
/test-root/tenant-A/document.txt
/test-root/tenant-B/marker.txt
/test-root/tenant-A-backup/marker.txt
```

Các đường dẫn trên chỉ minh họa fixture. Môi trường thực cần dùng namespace riêng của bài thử và có cách quan sát đọc, ghi, xóa. Không sử dụng dữ liệu bí mật thật làm tệp đánh dấu.

Kiểm tra hai lớp:

- API công khai phải từ chối giá trị không phải ID và không cho truy cập ngoài quyền.
- Adapter storage phải giữ ranh giới khi nhận một tham chiếu không hợp lệ trong bài thử tiêm lỗi có kiểm soát, kể cả khi tham chiếu đến từ metadata hoặc job.

Chỉ kiểm tra API trả lỗi chưa chứng minh không có thao tác ngoài phạm vi xảy ra trước đó. Cần đối chiếu dấu vết I/O, nội dung marker và các tác động phụ tương ứng.

### 12.2. Trường hợp hợp lệ và quyền đối tượng

```gherkin
Given người dùng U có quyền đọc tài liệu A trong tenant của mình
And tài liệu ở phiên bản và trạng thái được phép phục vụ
When U tải bằng file_id hợp lệ
Then chỉ nội dung đúng tài liệu A được trả về
And audit liên kết đúng chủ thể, hành động và phiên bản

When U yêu cầu file_id hợp lệ của tenant B mà U không có quyền
Then không có nội dung hoặc metadata nhạy cảm của B được trả về
And hệ thống không dùng định danh đó để bỏ qua kiểm tra quyền
```

Trường hợp hợp lệ giúp tránh một bản sửa chỉ chặn mọi yêu cầu rồi được coi là an toàn. Lặp kịch bản cho preview, bản chuyển đổi và export thuộc phạm vi.

### 12.3. Cú pháp và nhiều tầng giải mã

Kiểm tra thành phần thư mục cha, đường dẫn tuyệt đối, dấu phân cách khác, tên có ký tự điều khiển, biểu diễn mã hóa và đầu vào quá dài. Với hợp đồng chỉ nhận ID, tất cả giá trị ngoài grammar phải bị từ chối trước I/O tài nguyên.

Trên các nền tảng và backend được sản phẩm hỗ trợ, bổ sung dạng ổ đĩa, UNC, namespace đặc biệt, stream và alias có liên quan. Kiểm tra qua proxy, route, API và worker để chứng minh không có tầng sau biến dữ liệu đã kiểm tra thành đường dẫn khác.

Không chỉ chạy chuỗi kiểm thử trên một hệ điều hành rồi suy ra bảo đảm cho mọi môi trường. Dạng không được endpoint hỗ trợ vẫn phải bị từ chối theo hợp đồng; ngữ nghĩa của backend được hỗ trợ cần có bài thử riêng.

### 12.4. Root có cùng prefix và lỗi ánh xạ

Trong bài thử adapter, đưa một tham chiếu trỏ tới `tenant-A-backup` khi root được phép là `tenant-A`. Kết quả phải là không có I/O ngoài phạm vi, không phải chấp nhận vì chuỗi bắt đầu giống root.

Thử cấu hình root thiếu, root không truy cập được và ánh xạ tài nguyên rỗng. Hệ thống không được chuyển sang thư mục hiện tại, root cha hoặc tham chiếu do client cung cấp. Phản hồi không được lộ cấu trúc đường dẫn vật lý.

### 12.5. Liên kết và thay đối tượng đồng thời

Tạo cấu trúc liên kết hoặc chuyển hướng phù hợp với nền tảng và mô hình đe dọa trong vùng thử nghiệm. Bao gồm thành phần cuối và thư mục trung gian, không chỉ tệp đích.

Nếu có khoảng giữa kiểm tra và mở, dùng điểm đồng bộ để thử thay thành phần trong khoảng đó. Kết quả cho phép là từ chối hoặc tiếp tục trên đúng đối tượng được ràng buộc trước đó theo hợp đồng; không được đọc hay ghi tệp đánh dấu bên ngoài.

Nếu thiết kế đã ngăn quyền tạo hoặc thay liên kết, bài thử cần chứng minh hành động thay bị ngăn ở ranh giới tương ứng. Không giả định rằng chỉ cần bật cờ không đi theo symlink là đã bao phủ hard link, junction và mount point trong mọi môi trường.

### 12.6. Tạo, thay thế và xóa

Cho hai thao tác khác nhau cùng tạo một khóa đích mà chính sách yêu cầu độc quyền. Chỉ một đối tượng mới được tạo; thao tác còn lại không được ghi đè byte hoặc chuyển sang một đích khác ngoài hợp đồng.

Thử thay thế khi không có quyền, đổi nguồn hoặc đích sang namespace khác, và cập nhật phiên bản trong lúc thao tác đang chờ. Quyết định cũ không được tự chuyển sang đối tượng mới.

Với xóa, dùng marker để chứng minh ID rỗng, tham chiếu lỗi, job cũ và cleanup chạy lại không xóa thư mục cha hoặc phiên bản khác. Nếu có xóa đệ quy, kiểm tra quyền riêng và toàn bộ cây được duyệt theo chính sách liên kết.

### 12.7. Archive và thứ tự entry

Tạo archive thử nghiệm có entry hợp lệ cùng các trường hợp tên thoát root, đường dẫn tuyệt đối, kiểu liên kết không được phép, entry lặp và tên va chạm theo backend. Thử thứ tự trong đó một entry làm thay cấu trúc rồi entry sau sử dụng tên đó.

Không entry nào được ghi ngoài staging. Nếu chính sách là từ chối toàn bộ import khi có entry lỗi, không được phát hành phần kết quả còn lại như một import hoàn chỉnh. Cleanup chỉ tác động staging của job.

Kiểm tra ngân sách dựa trên byte giải nén thực, độ sâu và số entry, không chỉ trên metadata khai báo. Archive đầu ra cũng cần được kiểm tra tên entry và việc không đưa đường dẫn nội bộ vào sản phẩm tải xuống.

### 12.8. Metadata, job, URL và cache

Đưa tham chiếu không hợp lệ vào metadata hoặc payload job bằng cơ chế tiêm lỗi của môi trường thử nghiệm. Worker phải từ chối theo cùng ranh giới, không tin dữ liệu chỉ vì nó đã được lưu trước đó.

Làm nóng cache bằng người có quyền rộng rồi yêu cầu bằng người có quyền hẹp. Kết quả không được mở rộng quyền. Thử yêu cầu ký URL cho khóa, phiên bản hoặc bucket không thuộc tài nguyên đã cho phép; hệ thống không được cấp một quyền sử dụng hợp lệ cho sai đối tượng.

## 13. Truy vết tới kiến trúc và vòng đời phát triển

| Rủi ro | Yêu cầu liên quan | Điểm chịu trách nhiệm | Bằng chứng chính |
|---|---|---|---|
| Đầu vào trở thành địa chỉ tùy ý | PT-01, PT-03, PT-04 | API, ánh xạ tài nguyên và chuẩn hóa | Grammar, luồng giải mã và tham chiếu thực tới I/O |
| Đọc dữ liệu tenant khác | PT-02, PT-11 | Chính sách quyền, storage và cache | Quyền đối tượng, URL và nội dung trả về |
| Phân giải ra ngoài root | PT-05, PT-06, PT-07 | Adapter I/O, filesystem hoặc backend | Marker, liên kết và loại đối tượng thực |
| Ghi đè hoặc xóa sai dữ liệu | PT-08, PT-09 | Tạo độc quyền, quản lý phiên bản và cleanup | Nội dung trước sau, đối tượng và phạm vi xóa |
| Archive tạo dữ liệu ngoài staging | PT-10 | Bộ import và vùng tạm | Tên entry, thứ tự tạo và vị trí ghi thực |
| Fallback hoặc cấu hình mở rộng quyền | PT-03, PT-12 | Quản trị cấu hình và xử lý lỗi | Cấu hình lỗi, hành vi từ chối và audit |

Ở giai đoạn phân tích, liệt kê tài nguyên, thao tác, điểm vào và bên có thể thay tên hoặc cấu trúc. Chốt ranh giới tenant, namespace và giả định về quyền ghi của các tiến trình khác.

Ở giai đoạn thiết kế, chọn hợp đồng ID, ánh xạ phía máy chủ, root có thẩm quyền và cơ chế I/O phù hợp nền tảng. Đưa liên kết, thao tác đồng thời và đường xóa vào thiết kế ngay từ đầu.

Ở giai đoạn triển khai và nghiệm thu, gắn mã yêu cầu với từng đường thao tác. Kiểm thử cả luồng hợp lệ, trường hợp bị từ chối, dữ liệu gián tiếp và tác động thực tế trên backend.

Ở giai đoạn vận hành, theo dõi quyết định bị từ chối, lỗi root, thay đổi cấu hình và sai lệch cleanup. Khi thêm một endpoint, worker, thư viện archive hoặc storage mới, đánh giá lại các giả định phân giải và quyền truy cập.

## 14. Những lỗi đặc tả thường gặp

| Cách đặc tả dễ gây lỗi | Khoảng hở | Cách làm rõ |
|---|---|---|
| “Xóa chuỗi `../` là đủ” | Còn cú pháp, mã hóa và namespace khác | Dùng hợp đồng định danh và ngữ nghĩa backend rõ ràng |
| “Tên bắt đầu bằng root” | Prefix ký tự không phải ranh giới thành phần | Đối chiếu containment đúng và cưỡng chế tại I/O |
| “Canonical path đã đúng nên mở lại được” | Đối tượng có thể đổi sau kiểm tra | Giữ ràng buộc với đối tượng thực và xử lý TOCTOU |
| “Chặn symlink cuối đường dẫn” | Thư mục cha hoặc cơ chế liên kết khác vẫn có thể đổi đích | Chính sách trên toàn đường đi và đúng nền tảng |
| “Dữ liệu từ DB hoặc queue là tin cậy” | Tham chiếu có thể bắt nguồn từ client hoặc đã cũ | Thực thi ranh giới trên mọi đường sử dụng |
| “Có ID ngẫu nhiên nên không cần quyền” | Người biết ID vẫn truy cập được tài nguyên khác | Phân quyền theo chủ thể, tenant, đối tượng và hành động |
| “Chỉ đọc nên không có rủi ro” | Có thể lộ cấu hình hoặc dữ liệu nhạy cảm | Bảo vệ đọc, preview, metadata và export |
| “Không có tệp thì chuyển sang thư mục cha” | Fallback mở rộng phạm vi | Lỗi phải từ chối, không đổi root ngoài hợp đồng |
| “URL đã ký nên chắc đúng tài nguyên” | Máy chủ có thể ký sai ánh xạ | Kiểm tra quyền trước khi cấp đúng tham chiếu |
| “API trả lỗi nghĩa là chưa có tác động” | I/O có thể đã xảy ra trước khi trả lỗi | Đối chiếu đọc, ghi, xóa và marker ngoài phạm vi |

## 15. Bài tập tự kiểm tra

Một hệ thống nhận tên báo cáo từ client, ghép với root tenant rồi kiểm tra chuỗi kết quả có bắt đầu bằng root không. Khi mở lỗi, hệ thống thử lại trong thư mục cha. Tên báo cáo cũng được lưu vào job xóa; worker xem dữ liệu từ queue là tin cậy. Tính năng import giải nén trực tiếp vào thư mục tài liệu và cho phép công cụ tự xử lý entry trùng.

Hãy thực hiện các việc sau:

1. Xác định tài sản, thao tác và các đầu vào đang vượt qua ranh giới tin cậy.
2. Viết lại hợp đồng API dùng ID và ánh xạ tài nguyên phía máy chủ.
3. Đặc tả root, namespace, liên kết, loại đối tượng và xử lý thay đổi đồng thời.
4. Viết yêu cầu riêng cho tạo mới, thay thế, xóa và cleanup chạy lại.
5. Thiết kế staging và quy tắc entry cho import archive.
6. Viết ba bài kiểm thử có marker: prefix gần giống, tham chiếu gián tiếp trong job và entry archive ngoài phạm vi.
7. Xác định audit cần có để chứng minh không chỉ phản hồi mà tác động thực tế cũng tuân quyền.

Một lời giải đầy đủ cần nối quyền nghiệp vụ với đối tượng mà backend thực sự thao tác, qua mọi bước giải mã, ánh xạ và phân giải. Phòng vệ path traversal có thể kiểm chứng khi đầu vào không tin cậy không thể mở rộng namespace hoặc thay đối tượng được phép tại điểm I/O, kể cả trong đường lỗi và tác vụ nền.
