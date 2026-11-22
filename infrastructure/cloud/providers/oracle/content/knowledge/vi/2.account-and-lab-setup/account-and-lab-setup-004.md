# Điều hướng OCI Console và tìm kiếm tài nguyên

OCI Console là giao diện web để xem và quản lý tài nguyên Oracle Cloud Infrastructure. Người học thường bắt đầu bằng việc mở đúng dịch vụ, nhưng thao tác chính xác còn phụ thuộc vào **tenancy, region, compartment, bộ lọc và quyền của danh tính đang đăng nhập**.

Một danh sách trống không nhất thiết có nghĩa tài nguyên chưa được tạo. Có thể bạn đang ở region khác, chọn compartment cha nhưng chưa bao gồm compartment con, giữ bộ lọc từ lần trước hoặc không có quyền xem. Ngược lại, thấy một tài nguyên cùng tên cũng chưa đủ để kết luận đó là tài nguyên của bài thực hành.

Bài học này hướng dẫn điều hướng Console và tìm kiếm tài nguyên theo cách có thể kiểm chứng. Các bước thực hành chỉ yêu cầu đọc thông tin; không cần tạo Compute, database hoặc tài nguyên tính phí để hoàn thành bài.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Xác định đúng tenancy, danh tính, region và compartment trước khi tìm tài nguyên.
- Mở một dịch vụ từ menu hoặc công cụ tìm kiếm của Console.
- Phân biệt tìm dịch vụ, tìm tài liệu và tìm tài nguyên thực tế.
- Tìm tài nguyên theo tên, loại, compartment hoặc OCID.
- Đọc trang chi tiết để xác nhận đúng đối tượng trước khi thao tác.
- Xử lý có hệ thống tình huống danh sách hoặc kết quả tìm kiếm trống.
- Ghi lại thông tin cần thiết để quay lại tài nguyên và trao đổi với người hỗ trợ.

Tên nhóm menu, vị trí nút và phạm vi của từng công cụ có thể thay đổi theo dịch vụ hoặc giao diện. Vì vậy, hãy dựa vào ý nghĩa của các vùng điều hướng và thông tin thực tế được hiển thị, thay vì học thuộc vị trí tuyệt đối của một nút.

## 2. Nắm ngữ cảnh trước khi điều hướng

### 2.1. Năm câu hỏi cần trả lời

Trước khi tìm một tài nguyên, hãy xác định:

| Câu hỏi | Thông tin cần kiểm tra | Ví dụ trong bài |
| --- | --- | --- |
| Đang ở hệ thống nào? | Tenancy | Tenancy học tập do tổ chức cấp |
| Đăng nhập bằng ai? | Người dùng hoặc danh tính, identity domain nếu liên quan | Tài khoản học viên |
| Tìm ở vùng nào? | Region | Region do người hướng dẫn chỉ định |
| Tìm trong phạm vi quản trị nào? | Compartment | learning-lab |
| Đang lọc những gì? | Trạng thái, tên, tag hoặc điều kiện khác | Chỉ hiện tài nguyên đang chạy |

Tên **learning-lab** trong bài chỉ là ví dụ. Không tự tạo hoặc đổi tên compartment để khớp với ví dụ.

Nếu thiếu region hoặc compartment của tài nguyên cần tìm, nên lấy thông tin từ yêu cầu bài lab hoặc người quản lý môi trường trước khi kết luận tài nguyên không tồn tại.

### 2.2. Tenancy khác identity domain

Tenancy là phạm vi tài khoản cloud chứa các tài nguyên và cấu trúc quản trị liên quan. Identity domain tổ chức việc quản lý danh tính và truy cập theo cấu hình của tenancy.

Có thể có nhiều cách đăng nhập hoặc nhiều domain được sử dụng. Hai người cùng mở Console nhưng dùng danh tính khác nhau có thể thấy các tập tài nguyên khác nhau do IAM.

Không nên cố tìm một instance trong một tenancy khác chỉ vì tên người dùng giống nhau. Cũng không nên suy ra mọi người đăng nhập cùng tenancy đều có cùng quyền.

### 2.3. Region khác availability domain

Region là khu vực triển khai của nhiều tài nguyên OCI như VCN và Compute instance. Availability domain là phạm vi hạ tầng bên trong một region theo thiết kế OCI.

Khi tìm instance ở region A, chuyển bộ lọc availability domain trong region B không giúp tìm được instance đó. Trước hết phải chọn đúng region.

Tài nguyên và thao tác thuộc IAM có quy tắc phạm vi riêng; không áp dụng máy móc cách lọc instance theo region cho toàn bộ dịch vụ quản trị danh tính.

### 2.4. Compartment là phạm vi quản trị, không phải region

Một compartment không bị giới hạn theo cách “mỗi compartment chỉ chứa tài nguyên của một region”. Cùng một compartment có thể được dùng để tổ chức tài nguyên tại nhiều region, tùy loại tài nguyên.

Vì vậy, khi chọn compartment learning-lab nhưng danh sách Compute trống, vẫn cần kiểm tra region. Chọn đúng compartment không thay thế việc chọn đúng vùng.

Tên compartment cũng có thể giống nhau ở những nhánh khác nhau. Khi cần xác nhận, hãy đối chiếu đường dẫn phân cấp và compartment OCID, không chỉ nhãn hiển thị.

## 3. Nhận biết các vùng chính của Console

### 3.1. Các vùng chức năng thường gặp

| Vùng | Công dụng | Điểm cần chú ý |
| --- | --- | --- |
| Thanh đầu trang | Truy cập tìm kiếm, region và thông tin tài khoản theo giao diện | Kiểm tra region trước khi đọc danh sách regional |
| Menu điều hướng dịch vụ | Mở Compute, Networking, Storage, Database, IAM và các nhóm khác | Tìm theo chức năng, không cần nhớ vị trí nút |
| Trang danh sách | Xem tập tài nguyên của một loại | Đọc compartment, bộ lọc và phân trang |
| Bộ chọn compartment | Chọn phạm vi hiển thị hoặc thao tác | Kiểm tra cách bao gồm compartment con |
| Breadcrumb hoặc đường dẫn | Biết đang ở trang nào và quay về cấp trước | Không dùng làm bằng chứng duy nhất về tài nguyên |
| Trang chi tiết | Xem định danh, trạng thái và cấu hình của một tài nguyên | Xác nhận OCID trước thao tác thay đổi |
| Tab hoặc nhóm tài nguyên liên quan | Đi tới VNIC, volume, subnet hoặc thành phần phụ thuộc | Phân biệt tài nguyên đang xem với tài nguyên vừa mở |
| Menu hành động | Thực hiện các thao tác mà quyền và trạng thái cho phép | Một số thao tác thay đổi hoặc xóa tài nguyên |

Menu có thể cho phép bạn mở trang của một dịch vụ ngay cả khi không có quyền xem tài nguyên trong compartment cụ thể. Mở được trang Compute không đồng nghĩa được phép quản lý mọi instance.

### 3.2. Đường điều hướng khái quát

~~~mermaid
flowchart TD
    A["Đăng nhập đúng tenancy và danh tính"] --> B["Xác nhận region khi tài nguyên có phạm vi regional"]
    B --> C{"Chọn cách đến tài nguyên"}
    C --> D["Menu dịch vụ"]
    C --> E["Tìm kiếm tài nguyên"]
    D --> F["Trang danh sách: compartment và bộ lọc"]
    E --> G["Kết quả: loại, vùng và phạm vi được hiển thị"]
    F --> H["Trang chi tiết"]
    G --> H
    H --> I["Đối chiếu OCID, compartment, region và trạng thái"]
~~~

Có hai lối đi chính tới cùng một tài nguyên: theo dịch vụ hoặc qua tìm kiếm. Dù đi bằng cách nào, bước xác nhận ở trang chi tiết vẫn cần thiết.

### 3.3. Không nhầm điều hướng với thao tác

Mở trang chi tiết, xem tab hoặc sao chép OCID thường là thao tác đọc. Các hành động như tạo, cập nhật, chuyển compartment, dừng, chấm dứt hoặc xóa có thể thay đổi tài nguyên.

Trước khi bấm một nút hành động, cần hiểu:

- Đối tượng mà nút tác động đến.
- Trạng thái hiện tại và điều kiện cho phép.
- Những tài nguyên hoặc dữ liệu liên quan.
- Yêu cầu của bài lab và quyền được giao.

Trong bài này, không cần thử các nút thay đổi để chứng minh đã tìm đúng tài nguyên.

## 4. Cách thứ nhất: đi từ dịch vụ đến tài nguyên

### 4.1. Xác định loại tài nguyên

Từ mô tả nghiệp vụ, hãy chuyển sang loại tài nguyên OCI phù hợp:

| Nhu cầu tìm | Dịch vụ hoặc từ khóa nên mở |
| --- | --- |
| Máy ảo hoặc bare metal instance | Compute, Instances |
| Mạng riêng VCN | Networking, Virtual Cloud Networks |
| Subnet | Chi tiết VCN tương ứng hoặc trang subnet mà giao diện cung cấp |
| Object Storage bucket | Object Storage, Buckets |
| Block volume | Block Storage, Block Volumes |
| Một dịch vụ database | Đúng nhóm database và đúng loại dịch vụ được triển khai |
| Người dùng, nhóm, compartment, policy | Nhóm quản trị danh tính và truy cập phù hợp |

“Database” là một nhóm rộng. Nếu bài lab dùng một loại dịch vụ database cụ thể, việc mở một trang danh sách của loại database khác có thể dẫn đến kết quả trống.

Tương tự, object nằm trong bucket không phải một Compute instance hay một volume. Cần tìm đúng loại trước khi áp dụng bộ lọc tên.

### 4.2. Ví dụ tìm một Compute instance

Giả sử được giao tìm một instance có:

~~~text
Tên hiển thị: lab-web-01
Region:      vùng được chỉ định trong bài lab
Compartment: learning-lab
OCID:        do người hướng dẫn cung cấp nếu đã có
~~~

Thực hiện:

1. Kiểm tra tenancy và danh tính đang đăng nhập.
2. Chọn đúng region của instance.
3. Mở nhóm Compute và trang Instances.
4. Chọn đúng compartment theo đường dẫn phân cấp.
5. Kiểm tra bộ lọc trạng thái, tên, tag và các điều kiện đang bật.
6. Nếu danh sách có nhiều trang, sử dụng tìm kiếm hoặc bộ lọc phù hợp thay vì chỉ nhìn trang đầu.
7. Mở instance có tên phù hợp.
8. Đối chiếu OCID, compartment và region trước khi kết luận.

Nếu có hai instance cùng tên, không chọn theo vị trí trong danh sách. Dùng OCID hoặc thông tin được giao để phân biệt.

### 4.3. Compartment con có được bao gồm không?

Giả sử cấu trúc quản trị là:

~~~text
Root
  + learning
      + learning-lab
      + learning-shared
~~~

Chọn compartment learning chưa chắc làm danh sách dịch vụ tự động hiển thị tài nguyên trong learning-lab.

Một số trang có lựa chọn bao gồm compartment con; cách hoạt động phụ thuộc trang. Hãy đọc nhãn và phạm vi hiển thị. Nếu chưa rõ, chọn trực tiếp learning-lab để kiểm tra.

Ngược lại, nếu bật bao gồm compartment con, kết quả có thể chứa tài nguyên ở nhiều nhánh. Khi đó, cần đọc cột compartment hoặc mở trang chi tiết để xác định vị trí chính xác.

### 4.4. Bộ lọc cũ có thể làm tài nguyên biến mất khỏi danh sách

Một số ví dụ:

- Chỉ hiển thị RUNNING nên không thấy instance STOPPED.
- Lọc theo tag của bài lab trước.
- Giữ nguyên chuỗi tìm kiếm không còn phù hợp.
- Chỉ xem một availability domain.
- Đang ở trang con chỉ liệt kê một loại tài nguyên liên quan.

Khi tìm không thấy, hãy ghi nhận các bộ lọc trước, sau đó xóa những điều kiện không cần thiết và kiểm tra lại. Không thay đổi tài nguyên để làm nó xuất hiện trong bộ lọc.

## 5. Cách thứ hai: dùng công cụ tìm kiếm của Console

### 5.1. Phân biệt ba mục đích tìm kiếm

Giao diện tìm kiếm có thể hiển thị các nhóm kết quả khác nhau:

| Nhóm kết quả | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Dịch vụ hoặc trang Console | Lối tắt tới chức năng | Compute, Virtual Cloud Networks |
| Tài nguyên | Đối tượng đang tồn tại mà bạn có quyền tìm thấy | Một instance hoặc VCN cụ thể |
| Tài liệu hoặc trợ giúp | Nội dung hướng dẫn | Bài hướng dẫn tạo VCN |

Tìm “Compute” rồi mở trang dịch vụ không có nghĩa bạn đã tìm thấy instance cần tìm. Tìm thấy tài liệu về bucket cũng không chứng minh tenancy đã có bucket đó.

Trước khi mở kết quả, đọc loại kết quả và những thông tin đi kèm.

### 5.2. Tìm theo tên

Khi biết tên hiển thị:

1. Mở vùng tìm kiếm của Console.
2. Chọn chế độ hoặc nhóm tìm tài nguyên nếu giao diện phân biệt các nhóm.
3. Nhập tên đầy đủ hoặc phần tên đủ đặc trưng.
4. Kiểm tra phạm vi region, loại tài nguyên và các bộ lọc đang áp dụng.
5. Đọc tất cả kết quả có khả năng phù hợp.
6. Mở trang chi tiết và đối chiếu định danh.

Không mặc định tìm theo một phần tên sẽ có cùng cách đối sánh với truy vấn có điều kiện bằng. Tìm văn bản và truy vấn có cấu trúc là hai cơ chế cần được hiểu riêng.

### 5.3. Tìm theo OCID

OCID giúp phân biệt chính xác hơn tên hiển thị. Nếu đã có OCID:

- Dùng trường tìm kiếm hoặc bộ lọc định danh mà công cụ hỗ trợ.
- Dán đầy đủ chuỗi, tránh ký tự thừa hoặc phần đã che bớt.
- Nếu công cụ hỗ trợ truy vấn theo thuộc tính định danh, chọn đúng thuộc tính được giao diện công bố.
- Nếu không có kết quả, mở trang danh sách của đúng loại tài nguyên và kiểm tra lại ngữ cảnh.

Một chuỗi OCID được dán vào vùng tìm tài liệu có thể không đưa tới tài nguyên. Không kết luận tài nguyên đã bị xóa chỉ từ một lần tìm ở sai nhóm kết quả.

Nếu có liên kết chi tiết do người hướng dẫn gửi, có thể mở liên kết sau khi xác minh nguồn và domain. Liên kết không bỏ qua đăng nhập, IAM hoặc các điều kiện truy cập khác.

### 5.4. Đọc phạm vi của Search

Không nên tự suy ra phạm vi tìm kiếm chỉ từ vị trí ô tìm kiếm ở đầu trang.

Hãy kiểm tra:

- Công cụ đang tìm loại tài nguyên nào?
- Đang áp dụng compartment cụ thể hay nhiều compartment?
- Phạm vi region được hiển thị là gì?
- Có chế độ nhiều region hoặc lựa chọn vùng riêng không?
- Những loại tài nguyên nào được dịch vụ tìm kiếm hỗ trợ?
- Những tài nguyên nào danh tính hiện tại có quyền thấy?

Nếu công cụ chỉ tìm trong region hiện tại, cần đổi region hoặc thực hiện lại ở vùng đích. Nếu công cụ cung cấp tìm kiếm nhiều region, phải kiểm tra những region thực sự được chọn.

Tìm trên nhiều compartment hoặc nhiều region vẫn không có nghĩa được vượt qua IAM. Công cụ cũng không thay thế mọi API danh sách chi tiết của từng dịch vụ.

## 6. Làm quen với tìm kiếm có cấu trúc

### 6.1. Khi nào nên dùng?

Khi số lượng tài nguyên lớn, tìm văn bản theo tên dễ trả về nhiều kết quả không liên quan. Tìm kiếm có cấu trúc giúp nêu rõ loại tài nguyên và điều kiện.

Trong giao diện hỗ trợ Structured Search của OCI Resource Search, các truy vấn cơ bản có dạng:

~~~text
query all resources
~~~

Truy vấn trên yêu cầu tìm các loại tài nguyên được công cụ hỗ trợ trong phạm vi tìm kiếm và quyền đang áp dụng. Nó không có nghĩa liệt kê mọi đối tượng của mọi dịch vụ OCI.

Để tập trung vào Compute instance:

~~~text
query instance resources
~~~

Tên loại tài nguyên trong ngôn ngữ truy vấn không nhất thiết giống nguyên văn nhãn menu. Nên sử dụng danh sách loại và gợi ý mà giao diện cung cấp khi viết truy vấn.

### 6.2. Tìm instance theo tên hiển thị

~~~text
query instance resources where displayName = 'lab-web-01'
~~~

Điều kiện này sử dụng thuộc tính displayName và phép so sánh bằng. Đây không phải cách yêu cầu tìm mọi tên có chứa một đoạn văn bản.

Nếu kết quả có nhiều dòng, vẫn phải đối chiếu compartment, region và OCID. Tên hiển thị không phải khóa duy nhất.

Nếu truy vấn không được chấp nhận, kiểm tra đúng chế độ Structured Search, tên loại và các thuộc tính được hỗ trợ trong giao diện. Không nhập nguyên cú pháp này vào trường lọc đơn giản của một trang danh sách rồi kỳ vọng nó hoạt động như trình truy vấn.

### 6.3. Tìm theo compartment

~~~text
query all resources where compartmentId = '<COMPARTMENT_OCID>'
~~~

Thay placeholder bằng OCID đầy đủ của compartment cần kiểm tra. Không thay bằng tên learning-lab.

Phép so sánh với compartmentId nhằm vào giá trị compartment của tài nguyên. Không tự suy ra truy vấn này sẽ bao gồm toàn bộ các compartment con chỉ vì chúng nằm dưới compartment được chỉ định.

Ví dụ, nếu instance thuộc learning-lab, truy vấn bằng OCID của learning có thể không trả về instance đó khi điều kiện yêu cầu đúng compartmentId của tài nguyên.

### 6.4. Kiểm tra điều kiện trước khi thêm độ phức tạp

Một cách xây dựng truy vấn dễ kiểm tra:

1. Bắt đầu bằng loại tài nguyên.
2. Xác nhận có kết quả trong phạm vi hiện tại.
3. Thêm một điều kiện tên hoặc compartment.
4. Kiểm tra kết quả sau từng bước.
5. Chỉ kết hợp thêm điều kiện khi đã hiểu cú pháp và thuộc tính được hỗ trợ.

Không thêm đồng thời nhiều bộ lọc rồi đoán nguyên nhân khi kết quả trống.

Cũng không sửa hoặc bỏ điều kiện bảo mật để làm công cụ tìm kiếm trả thêm kết quả. Điều kiện truy vấn và quyền IAM là hai lớp riêng.

## 7. Kết quả tìm kiếm chưa phải toàn bộ sự thật vận hành

### 7.1. Không phải mọi đối tượng đều nằm trong chỉ mục tìm kiếm

Công cụ tìm kiếm tài nguyên hỗ trợ những loại tài nguyên và thuộc tính nhất định. Một object bên trong bucket, một bảng trong database hoặc một file trong máy ảo không mặc nhiên là một kết quả độc lập trong Resource Search.

Khi cần tìm object, hãy mở đúng bucket và sử dụng cơ chế liệt kê hoặc tìm của Object Storage. Khi cần tìm bảng, sử dụng công cụ database và quyền database phù hợp.

Không nhầm quyền quản lý hạ tầng database với quyền truy vấn dữ liệu bên trong database.

### 7.2. Chỉ mục và danh sách có thể cập nhật khác thời điểm

Sau khi tài nguyên được tạo, đổi tên, chuyển compartment hoặc xóa, kết quả tìm kiếm và các danh sách có thể chưa phản ánh cùng lúc.

Khi có sự khác biệt:

- Kiểm tra lại thao tác trước đó đã hoàn tất hay còn đang xử lý.
- Làm mới trang hoặc truy vấn trong giới hạn hợp lý.
- Đọc trực tiếp trang chi tiết hoặc API của tài nguyên nếu có OCID.
- Đối chiếu region, compartment và danh tính.
- Không tạo lại tài nguyên chỉ vì Search chưa hiện kết quả.

Một kết quả tìm kiếm cũng có thể chứa thông tin cần được xác nhận lại khi mở trang chi tiết. Với thao tác thay đổi, hãy dựa vào tài nguyên đang được mở và thông tin hiện tại.

### 7.3. Kết quả rỗng không chứng minh không tồn tại

Một lần tìm có kết quả rỗng chỉ chứng minh rằng **công cụ không trả về tài nguyên trong điều kiện truy vấn, phạm vi và quyền ở thời điểm đó**.

Nó chưa đủ để kết luận:

- Tài nguyên chưa được tạo.
- Tài nguyên đã bị xóa.
- Tài nguyên không có ở region khác.
- Không ai trong tenancy có quyền thấy nó.
- Bài lab bị lỗi.

Cách diễn đạt này giúp người học tránh chạy lại bước tạo và phát sinh tài nguyên trùng.

## 8. Xác nhận ở trang chi tiết

### 8.1. Những thông tin nên đối chiếu

Khi mở một tài nguyên, hãy kiểm tra:

| Thông tin | Mục đích |
| --- | --- |
| Loại tài nguyên | Tránh nhầm instance, database, bucket hoặc thành phần liên quan |
| Tên hiển thị | Đối chiếu với yêu cầu, nhưng không dùng đơn lẻ |
| OCID hoặc định danh phù hợp | Xác nhận đúng đối tượng |
| Compartment | Xác nhận phạm vi quản trị |
| Region nếu tài nguyên có phạm vi regional | Xác nhận vùng triển khai |
| Trạng thái hiện tại | Hiểu tài nguyên đang sẵn sàng, dừng hay xử lý thao tác |
| Tag hoặc chủ sở hữu được ghi nhận | Phân biệt bài lab, môi trường và người phụ trách |
| Tài nguyên liên quan | Hiểu đối tượng đang gắn với mạng, volume hoặc dịch vụ nào |

Không phải mọi loại tài nguyên đều hiển thị cùng một bộ trường. Hãy tìm trường tương đương phù hợp với dịch vụ.

### 8.2. Đừng nhầm tài nguyên cha với tài nguyên con

Từ trang instance, bạn có thể mở VNIC, subnet hoặc boot volume. Sau khi chuyển trang, các nút hành động có thể tác động đến đối tượng mới.

Ví dụ:

~~~text
Instance
  -> VNIC
      -> Subnet
          -> VCN
~~~

Đây là chuỗi liên quan giữa các tài nguyên, không phải bốn cách gọi cùng một tài nguyên.

Trước khi thực hiện thao tác ngoài bài học này, hãy đọc lại tiêu đề trang và định danh. Breadcrumb hỗ trợ điều hướng nhưng không thay việc xác nhận đối tượng.

### 8.3. Trạng thái hiển thị cần được hiểu đúng

Một instance RUNNING không bảo đảm website bên trong đã sẵn sàng. Một database được liệt kê không chứng minh ứng dụng đã kết nối SQL thành công. Một bucket tồn tại không có nghĩa người dùng được phép đọc mọi object.

Trang chi tiết cho biết trạng thái và metadata theo dịch vụ. Kiểm tra chức năng ứng dụng là bước riêng.

Trong bài này, chỉ cần đọc và ghi nhận trạng thái; không cần dừng, khởi động lại hoặc xóa tài nguyên để thử.

## 9. Quy trình khi không tìm thấy tài nguyên

### 9.1. Kiểm tra từ ngữ cảnh đến công cụ

Thực hiện theo chuỗi sau:

~~~text
Đúng tenancy và danh tính?
           |
Đúng loại dịch vụ?
           |
Đúng region hoặc phạm vi region của Search?
           |
Đúng compartment và cách xử lý compartment con?
           |
Còn bộ lọc hoặc phân trang nào không?
           |
Tên/OCID và cú pháp truy vấn có đúng không?
           |
Loại tài nguyên có được Search hỗ trợ không?
           |
Quyền IAM và trạng thái thao tác gần đây?
~~~

Chuỗi này không bảo đảm mọi lỗi có cùng nguyên nhân, nhưng giúp loại bỏ những nhầm lẫn phổ biến trước khi yêu cầu thay quyền hoặc tạo lại tài nguyên.

### 9.2. Bảng tình huống thường gặp

| Hiện tượng | Khả năng cần kiểm tra | Cách xử lý phù hợp |
| --- | --- | --- |
| Danh sách instance trống | Sai region hoặc compartment | Đối chiếu thông tin bài lab |
| Chọn compartment cha nhưng không thấy tài nguyên con | Chưa bao gồm compartment con | Chọn trực tiếp compartment chứa tài nguyên |
| Chỉ thiếu một số instance | Bộ lọc trạng thái, tag hoặc trang hiện tại | Kiểm tra và điều chỉnh điều kiện hiển thị |
| Thấy hai tài nguyên cùng tên | Tên hiển thị bị trùng | Đối chiếu OCID, region và compartment |
| Search không thấy tài nguyên vừa tạo | Chỉ mục chưa cập nhật hoặc phạm vi không đúng | Kiểm tra trạng thái tạo, rồi đọc trực tiếp bằng định danh |
| Có liên kết nhưng trang báo lỗi truy cập | IAM, ngữ cảnh sai hoặc tài nguyên không còn | Xác nhận principal, region và định danh |
| Không thấy object khi tìm toàn cục | Đang tìm sai cấp đối tượng | Mở đúng bucket và dùng công cụ của Object Storage |
| Vừa chuyển compartment thì người học không thấy nữa | Chính sách hiệu lực có thể thay đổi | Kiểm tra quyền ở compartment đích với người quản lý |
| Mở trang dịch vụ được nhưng danh sách không xem được | Quyền vào giao diện không đồng nghĩa quyền đọc tài nguyên | Kiểm tra quyền cần thiết cho loại tài nguyên |

### 9.3. Đề nghị hỗ trợ với thông tin đủ dùng

Thay vì chỉ báo “không thấy tài nguyên”, nên cung cấp:

~~~text
Mục tiêu:        tìm Compute instance của bài lab
Tên hiển thị:   lab-web-01
Region kỳ vọng: region được giao
Compartment:    đường dẫn và OCID nếu được phép chia sẻ
Danh tính:      tài khoản/domain đang dùng theo quy định tổ chức
Cách đã thử:    trang Instances và tìm kiếm tài nguyên
Bộ lọc:         các điều kiện còn bật
Kết quả:        danh sách trống hoặc mã/thông báo lỗi
Thời điểm:      lúc kiểm tra gần nhất
~~~

Nếu đã có OCID của tài nguyên, gửi cho người hỗ trợ qua kênh được phép. Không gửi mật khẩu, private key, mã MFA hoặc token đăng nhập.

Ảnh chụp có thể hữu ích khi đã che thông tin cần bảo vệ, nhưng một mô tả rõ ngữ cảnh thường giúp điều tra nhanh hơn ảnh chỉ có danh sách trống.

## 10. Thực hành chỉ đọc

### 10.1. Chuẩn bị

Người hướng dẫn hoặc người quản lý lab cung cấp:

- Tenancy và tài khoản học tập.
- Region được phép sử dụng.
- Compartment được giao.
- Một tài nguyên có sẵn, ưu tiên VCN hoặc instance phục vụ bài học.
- Tên hiển thị và OCID nếu có.

Nếu tenancy chưa có tài nguyên mẫu, có thể thực hành mở trang dịch vụ và xác nhận ngữ cảnh; không cần tạo tài nguyên chỉ để làm xuất hiện một dòng kết quả.

Không đổi sang compartment của đội khác khi chưa được giao phạm vi sử dụng, dù bạn có thể nhìn thấy tên compartment đó.

### 10.2. Bước 1: ghi nhận ngữ cảnh

Ghi thông tin trong phần báo cáo học tập được cho phép:

| Thuộc tính | Giá trị cần điền |
| --- | --- |
| Tenancy | Tên hoặc mã nhận diện được phép sử dụng |
| Danh tính/domain | Theo tài khoản học tập |
| Region đích | Region được giao |
| Compartment | Đường dẫn phân cấp |
| Compartment OCID | OCID đầy đủ nếu cần đối chiếu |
| Tài nguyên mục tiêu | Loại, tên và OCID nếu đã có |

Không sao chép thông tin xác thực vào bảng này.

### 10.3. Bước 2: tìm bằng menu dịch vụ

1. Mở đúng nhóm dịch vụ.
2. Xác nhận region nếu áp dụng.
3. Chọn compartment chứa tài nguyên.
4. Ghi lại những bộ lọc đang bật.
5. Tìm tài nguyên mục tiêu và mở chi tiết.
6. Đối chiếu định danh với thông tin được giao.
7. Ghi nhận trạng thái, không thay đổi trạng thái.

Nếu không thấy, thực hiện quy trình kiểm tra ở phần 9 và ghi rõ điểm chưa xác minh được.

### 10.4. Bước 3: tìm bằng công cụ Search

1. Mở công cụ tìm kiếm của Console.
2. Chọn nhóm tài nguyên.
3. Tìm theo tên hoặc định danh bằng chức năng được hỗ trợ.
4. Kiểm tra phạm vi region và các điều kiện.
5. Mở kết quả phù hợp.
6. Xác nhận OCID trùng với tài nguyên đã mở ở bước trước.

Nếu có Structured Search, thử truy vấn theo loại tài nguyên và một điều kiện đơn giản. Không cần sử dụng mọi kiểu truy vấn để hoàn thành bài.

### 10.5. Bước 4: tìm một tài nguyên liên quan

Từ trang chi tiết, mở một liên kết liên quan được phép đọc:

- Với instance: xem VNIC hoặc subnet liên quan.
- Với VCN: xem một subnet có sẵn.
- Với bucket: xem thông tin cấu hình bucket; chỉ đọc nội dung object nếu được giao quyền và mục tiêu đó.
- Với database: xem phần thông tin hạ tầng hoặc mạng được phép, không tự thử đăng nhập dữ liệu.

Ghi rõ đối tượng mới khác tài nguyên ban đầu ở loại và định danh nào. Sau đó quay lại bằng đường điều hướng phù hợp.

### 10.6. Bước 5: kiểm chứng một tình huống danh sách trống

Có thể thay đổi **bộ lọc hiển thị** bằng một tên giả định không tồn tại trong danh sách, rồi quan sát kết quả trống. Sau đó xóa bộ lọc để khôi phục danh sách.

Bước này chỉ thay điều kiện xem, không tạo, đổi tên hoặc xóa tài nguyên.

Mục đích là chứng minh rằng danh sách trống có thể do điều kiện truy vấn, không phải do tài nguyên thực tế biến mất.

### 10.7. Kết quả cần nộp

Một báo cáo ngắn nên có:

- Ngữ cảnh tenancy, region và compartment đã kiểm tra.
- Loại và định danh tài nguyên đã xác nhận.
- Hai đường tìm kiếm đã sử dụng.
- Các bộ lọc có ảnh hưởng đến kết quả.
- Một tài nguyên liên quan đã mở và cách quay lại.
- Giải thích vì sao kết quả trống chưa chứng minh tài nguyên không tồn tại.

Nếu tài nguyên mẫu chưa được cung cấp hoặc quyền chưa đủ, ghi đúng giới hạn quan sát thay vì tự tạo tài nguyên hoặc đề nghị quyền quản trị toàn tenancy.

## 11. Xây dựng thói quen điều hướng dễ lặp lại

### 11.1. Dùng tên và tag nhất quán

Tên như lab-web-01 dễ tìm hơn một tên không gợi mục đích. Tag về môi trường, chủ sở hữu hoặc bài lab có thể giúp phân loại nếu tổ chức đã thiết lập quy ước.

Tuy nhiên:

- Tên không bảo đảm duy nhất.
- Tag có thể thiếu hoặc bị nhập sai.
- Tìm theo tag chỉ hữu ích khi công cụ và loại tài nguyên hỗ trợ.
- Tên và tag không thay thế quyền IAM hoặc OCID.

Trong bài điều hướng, chỉ đọc và nhận biết quy ước hiện có. Không tự thêm tag vào tài nguyên dùng chung.

### 11.2. Lưu liên kết cùng với ngữ cảnh

Bookmark hoặc liên kết chi tiết giúp mở lại nhanh, nhưng nên kèm:

- Loại tài nguyên.
- OCID.
- Region nếu áp dụng.
- Compartment.
- Vai trò trong bài lab.

Liên kết có thể không còn hữu ích nếu tài nguyên đã bị xóa, thay thế hoặc người dùng mất quyền. OCID mới của một tài nguyên tạo lại không được xem là OCID cũ chỉ vì tên không đổi.

Đừng dùng URL hoặc bookmark như nơi cất thông tin xác thực.

### 11.3. Gắn việc tìm kiếm với dọn dẹp lab

Khả năng tìm đúng tài nguyên giúp kiểm soát chi phí sau bài thực hành. Có thể dùng quy ước tên, tag, compartment và sổ tài nguyên để kiểm kê những thành phần đã tạo.

Tuy nhiên, kết quả Search không phải một bảng kê chi phí hoàn chỉnh. Một tài nguyên đang dừng vẫn có thể liên quan đến volume, backup hoặc thành phần khác còn tồn tại.

Việc dọn dẹp thuộc quy trình riêng: xác minh chủ sở hữu, dữ liệu cần giữ, tài nguyên phụ thuộc và quyền thao tác trước khi xóa. Bài này chỉ giúp định vị và đọc thông tin cần cho quy trình đó.

## 12. Tự kiểm tra

### Câu 1: Chọn đúng compartment có đủ để thấy mọi instance của bài lab không?

Chưa. Cần đúng region, loại tài nguyên, bộ lọc, phạm vi compartment con và quyền IAM phù hợp.

### Câu 2: Có hai kết quả cùng tên lab-web-01, nên chọn kết quả đầu tiên không?

Không. Hãy đối chiếu OCID, region, compartment và những thông tin được giao. Thứ tự kết quả không chứng minh tài nguyên nào đúng.

### Câu 3: Tìm từ khóa “VCN” và thấy bài hướng dẫn, vậy đã tìm được mạng của bài lab chưa?

Chưa. Đó là kết quả tài liệu. Cần mở kết quả tài nguyên hoặc trang danh sách VCN và xác nhận mạng cụ thể.

### Câu 4: Chọn compartment cha có luôn bao gồm tài nguyên trong compartment con không?

Không nên giả định như vậy. Kiểm tra cơ chế của trang đang dùng hoặc chọn trực tiếp compartment chứa tài nguyên.

### Câu 5: Search không thấy tài nguyên vừa tạo, có nên tạo lại ngay không?

Không. Cần xác nhận thao tác tạo, region, compartment, quyền và khả năng cập nhật chỉ mục; nếu có OCID thì kiểm tra trực tiếp bằng định danh.

### Câu 6: Truy vấn bằng compartmentId có thể thay tên compartment vào giá trị không?

Không. Thuộc tính compartmentId cần định danh compartment phù hợp, không phải tên hiển thị.

### Câu 7: Mở được trang chi tiết instance RUNNING có chứng minh website đã hoạt động không?

Không. Trạng thái hạ tầng khác kiểm tra mạng và sẵn sàng ứng dụng. Cần kiểm tra chức năng ứng dụng bằng quy trình tương ứng.

## 13. Danh sách kiểm tra trước khi kết luận đã tìm đúng tài nguyên

- [ ] Đúng tenancy và danh tính được giao.
- [ ] Đúng loại dịch vụ và loại tài nguyên.
- [ ] Đúng region hoặc đã kiểm tra phạm vi region của công cụ tìm.
- [ ] Đúng compartment, đường dẫn và cách xử lý compartment con.
- [ ] Đã kiểm tra bộ lọc, phân trang và chuỗi tìm kiếm còn lưu.
- [ ] Đã phân biệt kết quả dịch vụ, tài liệu và tài nguyên.
- [ ] Đã đối chiếu OCID hoặc định danh thích hợp trên trang chi tiết.
- [ ] Đã đọc trạng thái hiện tại và những tài nguyên liên quan cần thiết.
- [ ] Không dùng kết quả tìm kiếm rỗng làm bằng chứng duy nhất về việc không tồn tại.
- [ ] Không thực hiện thao tác thay đổi chỉ để kiểm tra khả năng điều hướng.

Điều hướng OCI Console hiệu quả bắt đầu từ việc giữ đúng ngữ cảnh và kết thúc bằng việc xác nhận đúng định danh. Khi nắm được hai bước này, người học có thể tìm tài nguyên trong nhiều dịch vụ mà không phụ thuộc vào vị trí cố định của một menu hoặc tên hiển thị có thể bị trùng.
