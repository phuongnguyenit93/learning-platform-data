# Sử dụng Cloud Shell và Code Editor

## Mục tiêu bài học

Sau bài học, bạn có thể mở Cloud Shell và Code Editor từ OCI Console, thực hiện một truy vấn OCI chỉ đọc, tạo một workspace học tập và biên dịch chương trình Java nhỏ. Bạn cũng có thể phân biệt quyền truy cập, đường mạng, region của phiên và nơi lưu tệp.

Bài học thuộc chương **Tài khoản và môi trường thực hành** của module CLOUD_PROVIDERS_ORACLE. Kết quả cần đạt là một môi trường thao tác có kiểm soát để tiếp tục học IAM, VCN, Compute, lưu trữ và dịch vụ cơ sở dữ liệu. Các bước thực hành không yêu cầu tạo VM, bucket hoặc database.

Những lệnh Bash trong bài chạy trong **Cloud Shell của OCI**. Nếu máy cá nhân dùng Windows, bạn vẫn nhập các lệnh đó trong terminal Cloud Shell trên trình duyệt.

## 1. Cloud Shell và Code Editor phối hợp như thế nào?

**Cloud Shell** là terminal chạy trên môi trường do OCI quản lý và được truy cập qua Console. **Code Editor** cung cấp giao diện sửa mã, mở workspace và làm việc với các tệp của phiên Cloud Shell.

Có thể chia công việc như sau:

| Công cụ | Công việc phù hợp |
| --- | --- |
| OCI Console | Quan sát tài nguyên, kiểm tra phạm vi và mở công cụ phát triển |
| Cloud Shell | Chạy CLI, kiểm tra môi trường, biên dịch và thực thi mã |
| Code Editor | Tạo, đọc, sửa và lưu mã nguồn trong workspace |
| Dịch vụ đích | Cung cấp tài nguyên mà CLI hoặc mã của bạn truy cập |

Tài liệu [Code Editor](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_intro.htm) mô tả việc tích hợp trực tiếp với Cloud Shell và các quy trình dịch vụ được hỗ trợ.

~~~mermaid
flowchart LR
    B["Trình duyệt / OCI Console"] --> E["Code Editor"]
    B --> T["Cloud Shell terminal"]
    E --> F["Tệp trong workspace của phiên"]
    T --> F
    T -->|"CLI: xác thực, IAM và mạng"| O["Dịch vụ OCI"]
~~~

Trong bài lab, bạn sửa một tệp Java bằng editor rồi dùng terminal để biên dịch chính tệp đó. Mở editor hoặc terminal chưa tự triển khai chương trình thành một dịch vụ cho người dùng.

## 2. Chuẩn bị quyền và phạm vi thực hành

Bạn cần đăng nhập đúng tenancy, dùng tài khoản được giao và có quyền sử dụng Cloud Shell. Một policy mẫu cho nhóm trong identity domain là:

~~~text
Allow group <DOMAIN_NAME>/<GROUP_NAME> to use cloud-shell in tenancy
~~~

Quản trị viên thay placeholder bằng tên thực và cấu hình policy đúng phạm vi. Policy Cloud Shell dùng phạm vi tenancy; xem [Cloud Shell — Required IAM Policy](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cloudshellintro.htm#Required_IAM_Policy).

Code Editor dùng chính sách truy cập Cloud Shell. Nếu sử dụng plugin dịch vụ, còn cần quyền của dịch vụ đó và quyền quan sát compartment theo tài liệu Code Editor.

Cần phân biệt ba điều kiện:

| Điều kiện | Ví dụ câu hỏi |
| --- | --- |
| Quyền mở công cụ | Tài khoản có được sử dụng Cloud Shell không? |
| Quyền thực hiện thao tác | Tài khoản có được liệt kê Compute instance trong compartment lab không? |
| Đường kết nối | Phiên có tiếp cận được endpoint cần gọi không? |

Ví dụ, người học mở được Cloud Shell nhưng chưa được xem instance vẫn có thể nhận lỗi quyền khi gọi Compute API. Ngược lại, đủ quyền IAM chưa bảo đảm có đường mạng tới một endpoint riêng.

Trong bài này, truy vấn Compute là bước tùy chọn nếu người học đã được cấp quyền đọc. Không cần cấp quyền quản trị toàn tenancy chỉ để thực hành editor và Java.

## 3. Mở Cloud Shell và xác nhận môi trường

### 3.1. Bắt đầu phiên

1. Đăng nhập OCI Console bằng tài khoản học tập.
2. Kiểm tra tenancy và region đang chọn.
3. Với lần thực hành đầu, chọn home region của tenancy và kiểm tra chế độ khởi chạy phiên.
4. Mở biểu tượng **Cloud Shell/Code Editor** trên thanh đầu trang.
5. Chọn **Cloud Shell** và chờ terminal sẵn sàng.

Các bước mở công cụ được trình bày tại [Using Cloud Shell](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/devcloudshellgettingstarted.htm).

Cloud Shell cung cấp OCI CLI đã được xác thực cho phiên. Vì vậy, bài lab không cần tạo thêm API key hoặc chạy lại quy trình cấu hình CLI của máy cá nhân.

### 3.2. Kiểm tra công cụ

Nhập từng lệnh trong terminal:

~~~bash
pwd
whoami
uname -m
oci --version
java -version
javac -version
~~~

Ý nghĩa của kết quả:

| Lệnh | Thông tin cần quan sát |
| --- | --- |
| pwd | Thư mục hiện tại |
| whoami | Tên người dùng hệ điều hành trong môi trường shell |
| uname -m | Kiến trúc của môi trường chạy |
| oci --version | Phiên bản CLI hiện có |
| java -version | Runtime Java đang dùng |
| javac -version | Trình biên dịch Java đang dùng |

Tên do whoami trả về là tên người dùng hệ điều hành; nó không phải bằng chứng đầy đủ về mọi quyền IAM của tài khoản OCI.

Không cần đầu ra trùng từng ký tự với một ảnh chụp hướng dẫn. Phiên bản công cụ có thể thay đổi; cần xác nhận lệnh tồn tại và phù hợp với mã sẽ chạy.

### 3.3. Kiểm tra Java runtime khi cần

Bạn có thể xem các Java runtime được hỗ trợ:

~~~bash
csruntimectl java list
~~~

Nếu cần đổi runtime, chọn alias thực tế từ danh sách và đọc trợ giúp trước:

~~~bash
csruntimectl help
~~~

Sau khi đổi, chạy lại java -version và javac -version. Không chọn một alias chỉ vì nó xuất hiện trong bài viết cũ.

Việc quản lý runtime được mô tả trong phần **Managing Language Runtimes** của tài liệu Using Cloud Shell.

## 4. Phân biệt region của phiên và region đích của CLI

Có hai vị trí cần quan sát:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Cloud Shell session region | Nơi chạy môi trường shell và workspace của phiên |
| OCI CLI target region | Region mà một lệnh OCI hướng đến |

Theo tài liệu Cloud Shell, phiên mặc định chạy tại home region; regional launch cho phép khởi chạy phiên tại region được chọn. Region đích mặc định của CLI lấy từ lựa chọn Console khi bắt đầu phiên và có thể khác session region.

Chuyển region trên Console trong lúc phiên đang mở không tự chuyển môi trường shell đang chạy. Với một lệnh cần phạm vi rõ ràng, có thể chỉ định --region.

### 4.1. Chọn phạm vi cho bài lab

Trong terminal, đặt các biến riêng cho bài học:

~~~bash
lab_region='<REGION_ID_THUC_TE>'
lab_compartment_ocid='<OCID_COMPARTMENT_LAB>'
~~~

Chỉ thay placeholder bằng thông tin được cấp cho môi trường học tập. Không dùng compartment production để làm thử.

Ví dụ dùng biến:

~~~bash
oci os ns get --region "$lab_region"
~~~

Chỉ định region không tự tạo kết nối mạng tới region đó. Nếu network mode chỉ cho tiếp cận dịch vụ trong session region, cần chọn lại phiên hoặc chế độ mạng phù hợp.

### 4.2. Workspace ở home region và ngoài home region

Tài liệu [Working with Workspaces](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_using_workspaces.htm) lưu ý rằng tệp của phiên ngoài home region là tạm thời. Cần sao lưu trước khi môi trường phiên bị chấm dứt.

Với bài học đầu tiên, dùng home region giúp đơn giản hóa việc tiếp tục công việc giữa các phiên. Dù vậy, dữ liệu học tập quan trọng vẫn cần một bản lưu độc lập.

Đừng nhầm trạng thái editor khôi phục được với cam kết rằng mọi tệp ở mọi region đều được giữ lại.

## 5. Thực hiện truy vấn OCI đầu tiên

### 5.1. Lấy Object Storage namespace

Chạy:

~~~bash
oci os ns get --region "$lab_region"
~~~

Đầu ra có dạng minh họa:

~~~json
{
  "data": "<object-storage-namespace>"
}
~~~

Namespace là định danh không gian tên Object Storage của tenancy, không phải tên bucket và không phải OCID của compartment. Tham khảo [OCI CLI — os ns get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/ns/get.html).

Có thể chỉ lấy giá trị:

~~~bash
oci os ns get --region "$lab_region" --query data --raw-output
~~~

Trong lệnh này:

- --region chọn region đích.
- --query data lấy trường data của phản hồi.
- --raw-output hiển thị giá trị chuỗi thay vì chuỗi JSON có dấu ngoặc kép.

Thao tác lấy namespace không tạo bucket hoặc tải dữ liệu lên dịch vụ.

### 5.2. Liệt kê instance trong compartment lab, nếu được cấp quyền

~~~bash
oci compute instance list \
  --compartment-id "$lab_compartment_ocid" \
  --region "$lab_region" \
  --all \
  --query 'data[].{name:"display-name",state:"lifecycle-state"}' \
  --output table
~~~

Dấu gạch chéo ngược ở cuối dòng là cách nối dòng của Bash. Không thêm ký tự sau dấu nối dòng.

Tài liệu [OCI CLI — compute instance list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/instance/list.html) mô tả tham số compartment, bộ lọc và phân trang. --all lấy các trang kết quả; biểu thức --query chọn tên và trạng thái để bảng dễ đọc.

Một kết quả rỗng chỉ cho biết lệnh không trả về instance trong phạm vi đang hỏi. Hãy đối chiếu region, compartment và bộ lọc với Console trước khi kết luận tài nguyên không tồn tại.

Nếu nhận lỗi quyền, ghi lại thao tác, phạm vi và mã lỗi để người quản trị kiểm tra. Phần thực hành Java tiếp theo không phụ thuộc vào việc liệt kê instance thành công.

## 6. Tạo workspace và mở trong Code Editor

### 6.1. Tạo thư mục học tập trong Cloud Shell

~~~bash
mkdir -p "$HOME/oci-labs/cloud-shell-editor"
cd "$HOME/oci-labs/cloud-shell-editor"
pwd
~~~

Biến HOME được sử dụng theo môi trường có sẵn; không gán lại biến này. Lưu đường dẫn tuyệt đối mà pwd trả về để mở đúng thư mục trong editor.

Cấu trúc dự kiến:

~~~text
oci-labs/
└── cloud-shell-editor/
    ├── HelloOci.java
    └── out/
~~~

Đây là các tệp người học sẽ tạo trong môi trường Cloud Shell của mình, không phải tài nguyên Compute hoặc database của tenancy.

### 6.2. Mở editor

Từ biểu tượng Cloud Shell/Code Editor trên Console, chọn **Code Editor**. Nếu có lựa chọn bố cục, có thể dùng editor và terminal cạnh nhau hoặc chuyển qua các tab.

Theo [Launching Code Editor](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_using_launching_code_editor.htm), Code Editor dùng session region của Cloud Shell và có yêu cầu riêng đối với cửa sổ trình duyệt. Nên thực hành bằng cửa sổ trình duyệt thông thường.

Dùng chức năng mở thư mục của editor, chọn đường dẫn tuyệt đối đã lấy từ pwd. Tên menu có thể thay đổi theo giao diện; kết quả cần đạt là cây tệp bên trái hiển thị đúng thư mục cloud-shell-editor.

### 6.3. Mở terminal đúng thư mục

Bạn có thể chọn Terminal trong menu editor hoặc bấm chuột phải thư mục và chọn **Open In Terminal**. Cách thứ hai mở terminal với thư mục được chọn làm thư mục hiện tại; xem [Starting a Terminal Session](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_using_starting_a_terminal_session.htm).

Trong terminal mới, chạy:

~~~bash
pwd
~~~

Nếu kết quả khác thư mục lab, chuyển về đường dẫn lab trước khi biên dịch. Nhiều lỗi “không tìm thấy tệp” bắt nguồn từ terminal đang ở một thư mục khác với thư mục editor hiển thị.

## 7. Viết và chạy một chương trình Java nhỏ

### 7.1. Tạo tệp bằng editor

Trong workspace, tạo tệp **HelloOci.java** và nhập:

~~~java
public class HelloOci {
    public static void main(String[] args) {
        String learner = args.length == 0 ? "learner" : args[0];
        System.out.println("Hello OCI, " + learner + "!");
    }
}
~~~

Lưu tệp rồi kiểm tra cây thư mục. Tên tệp phải trùng chính xác với tên public class, gồm cả chữ hoa và chữ thường.

Chương trình chỉ in một thông điệp. Nó không gọi OCI API, không cần OCI SDK và không chứa thông tin xác thực.

### 7.2. Kiểm tra tệp từ terminal

Trong terminal của thư mục lab:

~~~bash
pwd
ls -l HelloOci.java
sed -n '1,20p' HelloOci.java
~~~

Nếu không thấy nội dung vừa nhập, hãy kiểm tra tệp đã được lưu và editor có mở đúng workspace hay chưa.

### 7.3. Biên dịch và chạy

~~~bash
mkdir -p out

if javac -d out HelloOci.java; then
    java -cp out HelloOci "OCI learner"
fi
~~~

Kết quả mong đợi:

~~~text
Hello OCI, OCI learner!
~~~

Giải thích:

| Thành phần | Vai trò |
| --- | --- |
| javac | Biên dịch mã Java |
| -d out | Ghi tệp class vào thư mục out |
| java -cp out | Dùng out làm classpath |
| HelloOci | Tên lớp có phương thức main |
| "OCI learner" | Một đối số chuỗi truyền cho chương trình |

Khối if chỉ chạy chương trình khi biên dịch thành công. Điều này tránh chạy nhầm một tệp class cũ sau khi bản mã mới có lỗi.

### 7.4. Quan sát mối liên hệ editor và terminal

Đổi thông điệp trong editor, lưu tệp rồi biên dịch và chạy lại. Sau đó kiểm tra:

~~~bash
ls -l HelloOci.java out/HelloOci.class
~~~

Bạn cần quan sát được ba trạng thái khác nhau:

1. Nội dung trong tab editor.
2. Nội dung tệp đã lưu.
3. Bản class được tạo từ lần biên dịch thành công.

Lưu một tệp Java không tự biên dịch nó. Biên dịch thành công cũng không tự biến chương trình thành một ứng dụng web được triển khai trên OCI.

### 7.5. Nếu gặp lỗi

| Lỗi hoặc dấu hiệu | Cách kiểm tra |
| --- | --- |
| file not found | Chạy pwd và kiểm tra đường dẫn tệp |
| Public class phải nằm trong tệp cùng tên | Đối chiếu HelloOci với HelloOci.java |
| Lỗi cú pháp | Kiểm tra dấu ngoặc, dấu chấm phẩy và dấu nháy |
| Could not find or load main class | Kiểm tra classpath, tên lớp và kết quả biên dịch |
| Nội dung in ra vẫn cũ | Lưu tệp và biên dịch lại đúng thư mục |
| UnsupportedClassVersionError | Đối chiếu phiên bản javac tạo class với java đang chạy |

Bài thực hành dùng thư viện chuẩn nên không cần tải dependency. Nếu chạy được Java nhưng một dự án khác không tải được thư viện, cần kiểm tra thêm mạng và cấu hình kho dependency của dự án đó.

## 8. Hiểu các chế độ mạng trước khi gọi dịch vụ

Cloud Shell có các chế độ kết nối khác nhau:

| Chế độ | Mục đích |
| --- | --- |
| OCI Service Network | Tiếp cận dịch vụ OCI trong session region theo khả năng được hỗ trợ |
| Public Network | Kết nối internet khi được chính sách cho phép |
| Private Network Access | Kết nối tới mạng riêng đã cấu hình |

Tài liệu [Cloud Shell Networking](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cloudshellintro_topic-Cloud_Shell_Networking.htm) mô tả các chế độ này và quyền cần thiết. Public Network cần quyền riêng; Private Network cần lựa chọn mạng cùng các điều kiện về quyền, subnet và quy tắc kết nối.

Không nên coi việc mở được Console là bằng chứng terminal có thể truy cập mọi địa chỉ.

### 8.1. Phân biệt ba luồng

~~~text
Trình duyệt → OCI Console
Cloud Shell → API quản trị dịch vụ OCI
Cloud Shell → endpoint riêng của VM hoặc database
~~~

Ba luồng có điểm xuất phát, danh tính và điều kiện kết nối khác nhau.

Ví dụ, lệnh liệt kê thông tin database có thể thành công vì đang gọi API quản trị. Kết nối SQL tới database đó vẫn có thể thất bại do đường mạng, cấu hình TLS hoặc quyền trong database.

Tương tự, clone một repository công khai cần đường ra internet phù hợp. Lỗi tải mã không có nghĩa là tài khoản mất mọi quyền OCI.

### 8.2. Thao tác thay region không thay thế cấu hình mạng

Lựa chọn --region xác định đích API; nó không tạo route, không mở quy tắc mạng và không gắn phiên vào một private subnet.

Trước khi thử truy cập tài nguyên riêng, cần xác định endpoint, session region, network mode và phương thức xác thực của dịch vụ đích.

Trong bài lab cơ bản, không cần cấu hình Private Network hoặc cấp thêm đường internet để chạy chương trình Java ở trên. Chỉ thực hiện cấu hình bổ sung khi bài thực hành tiếp theo có yêu cầu rõ ràng.

### 8.3. Khi nào cần kiểm tra chính sách Public Network?

Nếu mục tiêu thực hành thực sự cần tải mã hoặc dependency từ internet, quản trị viên có thể đánh giá quyền Public Network theo chính sách của tenancy.

Không cần bật thêm quyền chỉ để làm cho một lệnh thử bất kỳ hoạt động. Hãy xác định trước nguồn tải, mục đích và phạm vi truy cập cần thiết.

## 9. Lưu công việc và tiếp tục ở phiên sau

### 9.1. Phân biệt các loại trạng thái

| Loại trạng thái | Ví dụ | Việc cần làm |
| --- | --- | --- |
| Nội dung chưa lưu trong editor | Thay đổi trong tab đang mở | Lưu tệp trước khi rời phiên |
| Tệp trong workspace | HelloOci.java | Xác định region và chính sách lưu giữ |
| Trạng thái terminal | Thư mục hiện tại, biến Bash | Chuẩn bị cách thiết lập lại khi mở phiên mới |
| Tiến trình đang chạy | Một tác vụ Java | Không dựa vào việc tab trình duyệt luôn mở |
| Tài nguyên OCI | VM hoặc bucket được tạo bằng API | Quản lý vòng đời độc lập với cửa sổ terminal |

Tệp còn tồn tại không có nghĩa biến shell hoặc tiến trình được khôi phục nguyên trạng.

Khi quay lại bài học, có thể bắt đầu bằng:

~~~bash
cd "$HOME/oci-labs/cloud-shell-editor"
pwd
ls -l HelloOci.java
java -version
~~~

Sau đó thiết lập lại các biến lab cần dùng. Không đưa mật khẩu hoặc token vào một tệp thiết lập để tiện tiếp tục bài học.

### 9.2. Lưu bản sao của mã nguồn

Một cách đơn giản là tải tệp nguồn về máy bằng chức năng Download của Cloud Shell. Với nhiều tệp, có thể đóng gói riêng thư mục lab:

~~~bash
tar -czf "$HOME/cloud-shell-editor-lab.tar.gz" \
  -C "$HOME/oci-labs" \
  cloud-shell-editor

tar -tzf "$HOME/cloud-shell-editor-lab.tar.gz"
~~~

Lệnh đầu tạo tệp nén trong home của phiên; lệnh sau liệt kê nội dung để kiểm tra. Sau đó dùng chức năng Download để lấy tệp nén về máy cá nhân và xác nhận đã tải thành công.

Chỉ tạo tệp nén trong cùng môi trường chưa tạo ra bản sao độc lập. Với phiên tạm thời, cần hoàn tất việc đưa bản sao ra nơi lưu bền vững trước khi kết thúc.

Chọn phạm vi nén theo dự án. Tránh nén toàn bộ home một cách tùy tiện vì có thể gom cả cấu hình, khóa hoặc dữ liệu không liên quan.

### 9.3. Backup không đồng nghĩa đồng bộ tự động

Oracle có hướng dẫn backup và restore home qua Object Storage trong tài liệu Using Cloud Shell. Bài này dùng cách tải riêng mã lab để không yêu cầu tạo thêm bucket.

Nếu dùng kho Git trong quy trình khác, cần kiểm tra nội dung trước khi đưa lên nơi chia sẻ. Tích hợp Git của editor là công cụ hỗ trợ; việc lưu tệp, tạo bản ghi phiên bản và đồng bộ tới máy chủ là những hành động riêng.

Không đưa secret vào mã nguồn rồi coi việc xóa khỏi bản mới là đã xử lý mọi bản sao trước đó.

## 10. Giới hạn sử dụng và lựa chọn môi trường phù hợp

Cloud Shell phục vụ thao tác tương tác và có giới hạn phiên, lưu trữ và mức sử dụng; tham khảo tài liệu Cloud Shell cùng [Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

Các quyết định cần nhớ:

| Nhu cầu | Hướng sử dụng |
| --- | --- |
| Học CLI, sửa script và chạy chương trình nhỏ | Cloud Shell và Code Editor |
| Giữ mã nguồn cần khôi phục | Có bản lưu độc lập theo quy trình dự án |
| Chạy tác vụ dài hoặc xử lý nặng | Chọn môi trường thực thi phù hợp |
| Phục vụ API cho người dùng | Triển khai lên nền tảng ứng dụng hoặc tài nguyên được thiết kế cho mục tiêu đó |
| Dùng database riêng | Cấu hình dịch vụ, kết nối và quyền dữ liệu tương ứng |

Cloud Shell được cung cấp miễn phí trong giới hạn áp dụng; tài nguyên mà bạn tạo hoặc dịch vụ mà bạn gọi vẫn chịu chính sách giá của chúng.

Đóng Cloud Shell không phải thao tác dọn VM, volume, bucket hoặc database đã tạo trước đó. Việc quản lý chi phí cần theo danh sách tài nguyên của lab.

Chương trình Java ở bài này kết thúc ngay sau khi in kết quả. Với các bài sau, cần chọn nơi chạy theo thời gian thực thi, tải, lưu trữ và mục tiêu sẵn sàng thay vì để một terminal học tập trở thành thành phần quan trọng của hệ thống.

## 11. Bảo vệ danh tính và dữ liệu trong môi trường thực hành

Cloud Shell sử dụng danh tính được cấp cho phiên, nên lệnh gọi OCI cần được đọc trước khi chạy.

Một thói quen tốt là kiểm tra:

- Lệnh đang đọc hay thay đổi tài nguyên?
- Region và compartment có đúng môi trường học tập không?
- Dữ liệu đầu vào có chứa bí mật không?
- Đầu ra có phù hợp để chia sẻ trong báo cáo không?
- Công cụ có yêu cầu thêm quyền hoặc kết nối mà bài học chưa cần không?

Trong editor, cần phân biệt **Save** với các thao tác của plugin như triển khai, gọi function hoặc chạy công việc hạ tầng. Sửa một tệp cấu hình và thực hiện thay đổi trên dịch vụ là các bước riêng.

Ví dụ, tài liệu [Editing a Configuration Using Code Editor](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/code-editor.htm) tách việc sửa cấu hình Resource Manager với các hành động plan và apply. Khi gặp nút thao tác dịch vụ, hãy đọc tác động thay vì chỉ dựa vào việc nó nằm trong editor.

Đối với báo cáo bài lab, chỉ cần ghi phiên bản công cụ, đường dẫn dự án, kết quả Java và phạm vi truy vấn. Không sao chép token, private key hoặc toàn bộ môi trường xác thực vào tài liệu.

## 12. Xử lý các lỗi thường gặp

| Dấu hiệu | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Không mở được Cloud Shell | Tài khoản, quyền mở công cụ, trạng thái trình duyệt | Đối chiếu IAM và thông tin lỗi; không tự cấp quyền rộng |
| Editor hoạt động không ổn định | Kiểu cửa sổ trình duyệt và phiên hiện tại | Dùng cửa sổ thông thường theo hướng dẫn Code Editor |
| Terminal mở nhưng API từ chối | Mã lỗi, danh tính và phạm vi lệnh | Kiểm tra quyền của thao tác và tài nguyên |
| Không tải được mã hoặc dependency | Network mode và đích truy cập | Xác nhận đường mạng phù hợp trước khi sửa mã |
| Không tới được database riêng | Endpoint, session region, Private Network và quyền dữ liệu | Phân tách lỗi mạng với lỗi xác thực database |
| Không thấy tệp vừa tạo | Workspace, thư mục hiện tại, tài khoản và session region | Chạy pwd, kiểm tra đường dẫn và bản lưu |
| Kết quả Java không đổi | Tệp đã lưu và lần biên dịch mới nhất | Biên dịch lại đúng tệp rồi mới chạy |
| Lệnh từ hướng dẫn báo lỗi cú pháp | Shell và ký tự sao chép | Dùng cú pháp Bash trong Cloud Shell; kiểm tra dấu nối dòng |

Một số trường hợp cần làm rõ thêm:

### 12.1. Console hoạt động nhưng terminal không kết nối

Cloud Shell sử dụng kết nối trình duyệt tới dịch vụ riêng của nó. Tài liệu Cloud Shell nêu yêu cầu WebSocket; proxy hoặc chính sách trình duyệt có thể ảnh hưởng việc mở phiên.

Hãy ghi thông báo lỗi cụ thể và kiểm tra với người quản lý môi trường khi cần. Việc truy cập được một trang Console không chứng minh mọi kết nối mà công cụ phát triển cần đều được cho phép.

### 12.2. CLI đã xác thực nhưng vẫn nhận lỗi

“Đã xác thực” trả lời danh tính đang dùng; “được phép” phụ thuộc IAM của từng thao tác. Cần kiểm tra đúng tenancy, compartment, region và tài nguyên liên quan.

Nếu phiên không còn hợp lệ, lưu công việc rồi mở phiên mới qua Console. Tránh sao chép thông tin xác thực của phiên cũ sang tệp riêng để cố giữ nó hoạt động.

### 12.3. Không thấy workspace ở phiên sau

Kiểm tra lại tài khoản và region của phiên trước. Không dùng thư mục home ở region khác như một kho dữ liệu đồng bộ sẵn.

Nếu bản mã cần giữ đã nằm trong một phiên tạm thời bị chấm dứt, không nên mặc định dịch vụ có thể phục hồi. Hãy xây thói quen tải hoặc lưu bản sao ngay trong quá trình thực hành.

### 12.4. Không thấy tài nguyên dù Console từng hiển thị

Đối chiếu các bộ lọc của Console với tham số CLI. Một lệnh có thể đang hỏi compartment hoặc region khác, hoặc dùng bộ lọc không phù hợp.

Chỉ chuyển sang thao tác thay đổi tài nguyên sau khi đã hiểu kết quả truy vấn. Không tạo lại tài nguyên chỉ vì một danh sách đang rỗng.

## 13. Kết thúc bài thực hành

Trước khi rời phiên, thực hiện theo thứ tự:

1. Lưu mọi tệp đang sửa.
2. Kiểm tra HelloOci.java bằng terminal.
3. Biên dịch và chạy thành công chương trình.
4. Tạo và kiểm tra bản sao của mã lab nếu cần giữ.
5. Xác nhận bản sao đã nằm ở nơi lưu độc lập.
6. Dừng tác vụ tương tác còn chạy.
7. Đóng hoặc kết thúc phiên bằng chức năng của công cụ.

Trong phạm vi bài này, các truy vấn OCI không tạo tài nguyên dịch vụ mới. Nếu bạn thực hiện thêm thao tác từ bài khác trong cùng phiên, hãy quản lý và kiểm tra tài nguyên phát sinh theo bài đó.

Không cần dùng lệnh xóa hàng loạt hoặc reset toàn bộ home để hoàn thành bài. Các tệp lab nhỏ có thể được giữ trong workspace để thực hành tiếp nếu phù hợp với chính sách lưu trữ.

## 14. Tiêu chí hoàn thành

Bạn hoàn thành bài học khi có thể chứng minh:

| Kết quả | Bằng chứng phù hợp |
| --- | --- |
| Mở được môi trường | Cloud Shell và Code Editor hoạt động với tài khoản được cấp |
| Biết phạm vi làm việc | Giải thích được session region, region đích và compartment lab |
| Dùng được OCI CLI | Lấy được namespace hoặc xác định rõ điều kiện còn thiếu của truy vấn |
| Dùng được workspace | Editor và terminal đọc cùng một tệp nguồn |
| Chạy được Java | Kết quả Hello OCI, OCI learner! xuất hiện sau khi biên dịch thành công |
| Hiểu lưu giữ dữ liệu | Xác định được tệp cần giữ và nơi có bản sao độc lập |
| Hiểu ranh giới quyền và mạng | Phân biệt quyền mở công cụ với quyền dịch vụ và đường kết nối |
| Kết thúc có kiểm soát | Đã lưu công việc và biết tài nguyên nào tồn tại ngoài vòng đời phiên |

Cloud Shell và Code Editor tạo một điểm khởi đầu thuận tiện để học OCI. Khi tiếp tục sang VCN, Compute, lưu trữ và cơ sở dữ liệu, hãy giữ cùng quy trình: **xác nhận phạm vi, kiểm tra quyền và mạng, thực hiện thao tác có mục đích, đọc kết quả và lưu công việc cần giữ**.
