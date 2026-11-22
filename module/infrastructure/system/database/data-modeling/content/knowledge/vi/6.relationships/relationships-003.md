# Vai trò của hai đầu quan hệ và cách đặt tên rõ nghĩa

Trong mô hình dữ liệu, một quan hệ cho biết các khái niệm nghiệp vụ liên kết với nhau như thế nào. Tuy nhiên, chỉ biết hai thực thể có liên quan là chưa đủ. Ta cần hiểu **mỗi bên tham gia quan hệ với vai trò gì**, một instance ở bên này có thể liên kết với bao nhiêu instance ở bên kia, và cách diễn đạt quan hệ sao cho người đọc không hiểu nhầm chiều hoặc ý nghĩa.

Ví dụ, câu “Khách hàng và đơn hàng có quan hệ với nhau” chưa cho biết khách hàng là người đặt, người thanh toán hay người nhận đơn. Một đơn hàng có thể được đặt bởi một khách hàng, được thanh toán bởi một chủ thể khác và được giao cho một người nhận khác. Nếu mô hình chỉ đặt tên quan hệ chung là “liên quan đến”, vai trò của các bên sẽ bị mờ đi.

Bài học này tập trung vào vai trò ở hai đầu quan hệ, cách đặt tên quan hệ theo ngữ nghĩa nghiệp vụ, cách biểu diễn quan hệ đệ quy và quan hệ có nhiều vai trò, đồng thời kiểm tra tên gọi cùng bội số để mô hình dễ đọc và nhất quán.

**Sau bài học, bạn có thể:**

- Giải thích vai trò của từng thực thể khi tham gia một quan hệ.
- Phân biệt tên quan hệ với tên vai trò ở mỗi đầu.
- Đặt tên quan hệ theo động từ hoặc cụm động từ có nghĩa rõ ràng.
- Đọc quan hệ theo cả hai chiều mà không đảo nhầm chủ thể và đối tượng.
- Nhận diện quan hệ đệ quy, quan hệ đối xứng và trường hợp một loại thực thể tham gia nhiều vai trò.
- Dùng vai trò để làm rõ khóa ngoại, quan hệ kết hợp và các quy tắc nghiệp vụ.

## 1. Vì sao cần xác định vai trò ở hai đầu quan hệ?

Một quan hệ kết nối các instance của những loại thực thể. Mỗi đầu quan hệ thể hiện cách một loại thực thể tham gia vào ý nghĩa nghiệp vụ đó. Vai trò giúp trả lời câu hỏi: **Instance này đang đóng vai gì trong quan hệ cụ thể?**

Xét câu:

> Một nhân viên phê duyệt yêu cầu nghỉ phép của một nhân viên khác.

Cả hai đầu đều là thực thể NHÂN VIÊN, nhưng vai trò khác nhau:

- Nhân viên ở đầu thứ nhất là **người phê duyệt**.
- Nhân viên ở đầu thứ hai là **người gửi yêu cầu**.

Nếu chỉ ghi quan hệ NHÂN VIÊN — liên quan — NHÂN VIÊN, người đọc không biết ai phê duyệt cho ai. Tên vai trò làm rõ ngữ nghĩa mà tên thực thể đơn thuần không thể hiện.

Một ví dụ khác:

> Một đơn hàng có địa chỉ thanh toán và địa chỉ giao hàng.

Cả hai địa chỉ đều có thể thuộc khái niệm ĐỊA CHỈ, nhưng trong đơn hàng chúng đảm nhận hai vai trò khác nhau:

- Địa chỉ thanh toán;
- Địa chỉ giao hàng.

Không nên suy ra rằng hai vai trò luôn có cùng giá trị. Một đơn có thể giao đến một nơi và xuất hóa đơn tới một nơi khác.

### 1.1. Ba thành phần cần phân biệt

Khi mô tả một quan hệ nhị phân, cần phân biệt:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Loại thực thể | Những loại đối tượng nào tham gia? | KHÁCH HÀNG và ĐƠN HÀNG |
| Tên quan hệ | Các đối tượng liên hệ với nhau bằng hành động hoặc ý nghĩa nào? | ĐẶT |
| Vai trò ở mỗi đầu | Mỗi đối tượng tham gia với tư cách gì? | Người đặt; đơn được đặt |

Có thể diễn đạt quan hệ bằng câu chủ động:

> Khách hàng **đặt** đơn hàng.

Và câu bị động tương ứng:

> Đơn hàng **được đặt bởi** khách hàng.

Hai câu mô tả cùng một quan hệ từ hai góc nhìn. Việc đặt tên tốt giúp cả hai câu đều dễ hiểu.

### 1.2. Vai trò thuộc về quan hệ, không nhất thiết là loại thực thể riêng

“Người mua”, “người nhận”, “người phê duyệt” có thể là vai trò của một cá nhân hoặc tổ chức trong một quan hệ. Không phải cứ có tên vai trò là phải tạo một bảng hoặc loại thực thể mới.

Ví dụ, một nhân viên có thể vừa là người gửi yêu cầu nghỉ phép vào tháng này, vừa là người phê duyệt yêu cầu của nhân viên khác trong một tình huống khác. Vai trò thay đổi theo từng quan hệ và từng ngữ cảnh.

Chỉ tạo loại thực thể riêng khi có định nghĩa, định danh, thuộc tính, vòng đời hoặc quy tắc độc lập được nghiệp vụ xác nhận.

## 2. Đặt tên quan hệ rõ nghĩa

Tên quan hệ nên diễn đạt điều xảy ra hoặc ý nghĩa liên kết giữa các thực thể. Với quan hệ nhị phân, động từ hoặc cụm động từ thường dễ đọc nhất.

Ví dụ:

- KHÁCH HÀNG **đặt** ĐƠN HÀNG.
- NHÂN VIÊN **phê duyệt** YÊU CẦU.
- ĐƠN HÀNG **được giao qua** KIỆN HÀNG.
- SẢN PHẨM **được phân loại vào** DANH MỤC.
- NHÂN VIÊN **báo cáo cho** NHÂN VIÊN QUẢN LÝ.

### 2.1. Ưu tiên tên thể hiện hành động hoặc ý nghĩa nghiệp vụ

Tên quan hệ như “có”, “liên quan”, “thuộc về” hoặc “kết nối với” thường quá chung nếu không có ngữ cảnh. Chúng có thể dùng trong trường hợp ý nghĩa thực sự là sở hữu hoặc liên kết chung, nhưng cần kiểm tra xem người đọc có suy ra đúng quy tắc không.

| Tên mơ hồ | Tên rõ hơn | Điều được làm rõ |
|---|---|---|
| KHÁCH HÀNG liên quan ĐƠN HÀNG | KHÁCH HÀNG đặt ĐƠN HÀNG | Khách hàng là chủ thể tạo giao dịch |
| NHÂN VIÊN có YÊU CẦU | NHÂN VIÊN gửi YÊU CẦU | Phân biệt người gửi với người phê duyệt |
| ĐƠN HÀNG có KIỆN | ĐƠN HÀNG được thực hiện qua KIỆN HÀNG | Làm rõ vai trò giao vận |
| SẢN PHẨM thuộc DANH MỤC | DANH MỤC phân loại SẢN PHẨM | Làm rõ hướng diễn đạt và ý nghĩa phân loại |
| NHÂN VIÊN nối NHÂN VIÊN | NHÂN VIÊN quản lý NHÂN VIÊN | Làm rõ quan hệ đệ quy |

Tên quan hệ không cần dài, nhưng phải phân biệt được với những quan hệ khác giữa cùng hai loại thực thể.

### 2.2. Dùng cùng một cách diễn đạt trong toàn mô hình

Nếu cùng một ý nghĩa được gọi là “đặt”, “tạo đơn”, “khởi tạo đơn” ở nhiều sơ đồ, hãy thống nhất tên chuẩn và ghi bí danh nếu cần. Không nên để tên quan hệ thay đổi tùy người vẽ sơ đồ.

Một tên chuẩn cần:

- Dùng từ ngữ quen thuộc với nghiệp vụ;
- Diễn đạt đúng hành động hoặc ý nghĩa;
- Phân biệt với quan hệ khác giữa cùng các thực thể;
- Ổn định trong tài liệu, mô hình và trao đổi nhóm;
- Có thể đọc thành câu từ cả hai phía.

Nếu thuật ngữ nghiệp vụ chưa thống nhất, hãy ghi câu hỏi cần xác nhận thay vì tự chọn một từ kỹ thuật rồi coi đó là định nghĩa.

## 3. Đặt tên vai trò ở hai đầu

Tên vai trò mô tả vị trí của một instance trong quan hệ. Có thể đặt tên theo danh từ hoặc cụm danh từ chỉ vai trò, ví dụ “người đặt”, “đơn được đặt”, “người quản lý”, “nhân viên được quản lý”.

Với quan hệ KHÁCH HÀNG — ĐẶT — ĐƠN HÀNG:

| Đầu quan hệ | Loại thực thể | Vai trò | Câu hỏi diễn giải |
|---|---|---|---|
| Đầu thứ nhất | KHÁCH HÀNG | Người đặt | Khách hàng này đặt những đơn nào? |
| Đầu thứ hai | ĐƠN HÀNG | Đơn được đặt | Đơn này được đặt bởi khách hàng nào? |

Tên vai trò hữu ích khi:

- Một loại thực thể tham gia quan hệ nhiều lần;
- Hai đầu có ngữ nghĩa khác nhau;
- Quan hệ được đọc từ nhiều hướng;
- Mô hình có nhiều khóa ngoại cùng tham chiếu một bảng;
- Cần phân biệt các trách nhiệm hoặc quyền hạn.

### 3.1. Vai trò và chiều đọc

Một quan hệ có thể được đọc theo hai chiều. Ví dụ:

- Khách hàng **đặt** đơn hàng.
- Đơn hàng **được đặt bởi** khách hàng.

Tên quan hệ có thể được đặt ở dạng chủ động, còn tên vai trò ở hai đầu giúp xác định chủ thể và đối tượng. Nếu dùng sơ đồ, hãy bảo đảm nhãn quan hệ và hướng mũi tên không mâu thuẫn với câu nghiệp vụ.

Không nên suy luận rằng chiều vẽ trái sang phải luôn là chiều nghiệp vụ. Sơ đồ có thể được bố trí theo không gian tùy ý; ý nghĩa phải nằm ở tên quan hệ, vai trò và ký hiệu bội số.

### 3.2. Vai trò không phải là bội số

Vai trò trả lời “instance tham gia với tư cách gì?”. Bội số trả lời “một instance có thể hoặc phải liên kết với bao nhiêu instance ở đầu kia?”.

Ví dụ, trong quan hệ quản lý:

- Vai trò: người quản lý và nhân viên được quản lý.
- Bội số: một người quản lý có thể quản lý nhiều nhân viên; mỗi nhân viên có tối đa một người quản lý trực tiếp.

Hai thông tin này bổ sung cho nhau, không thay thế nhau. Một tên vai trò rõ không thể bù cho bội số thiếu hoặc sai.

## 4. Kết hợp tên vai trò với bội số và tính tham gia

Mỗi quan hệ cần xác định số lượng tối thiểu và tối đa ở từng đầu. Thông thường có thể dùng ký hiệu:

| Ký hiệu | Diễn giải |
|---|---|
| 0..1 | Không có hoặc có tối đa một |
| 1..1 | Bắt buộc đúng một |
| 0..* | Không có hoặc có nhiều |
| 1..* | Có ít nhất một, có thể nhiều |

Ví dụ, trong quan hệ KHÁCH HÀNG đặt ĐƠN HÀNG:

- Một khách hàng có thể đặt 0 hoặc nhiều đơn.
- Một đơn đã được ghi nhận phải thuộc về đúng một khách hàng theo giả định hệ thống.

Có thể biểu diễn:

~~~mermaid
flowchart LR
    C["KHÁCH HÀNG<br/>Vai trò: người đặt"] -->|"đặt<br/>0..* đơn"| O["ĐƠN HÀNG<br/>Vai trò: đơn được đặt"]
    O -->|"được đặt bởi<br/>1 khách hàng"| C
~~~

Sơ đồ minh họa cách đọc hai chiều; các con số là giả định nghiệp vụ của ví dụ. Nếu hệ thống cho phép đơn khách vãng lai, quy tắc phía đơn có thể khác và cần mô hình hóa chủ thể mua phù hợp.

### 4.1. Tách bội số tối đa và tối thiểu

Đừng chỉ ghi “một-nhiều” nếu nghiệp vụ cần phân biệt trường hợp không có quan hệ.

Ví dụ:

- Một khách hàng có thể chưa đặt đơn nào: tối thiểu 0.
- Một đơn hàng đã xác nhận phải có ít nhất một dòng: tối thiểu 1.
- Một đơn nháp có thể chưa có dòng: ở trạng thái nháp, tối thiểu có thể là 0.

Tính tham gia có thể phụ thuộc trạng thái hoặc thời điểm. Nếu mô hình chỉ ghi bội số chung mà không nêu điều kiện, người đọc có thể hiểu sai.

### 4.2. Bội số cần đọc từ từng đầu

Khi đọc quan hệ, hãy hỏi riêng:

- Một instance ở đầu A liên kết tối thiểu và tối đa bao nhiêu instance ở đầu B?
- Một instance ở đầu B liên kết tối thiểu và tối đa bao nhiêu instance ở đầu A?

Việc đọc cả hai phía giúp tránh nhầm “mỗi đơn thuộc một khách hàng” thành “mỗi khách hàng chỉ có một đơn”.

## 5. Quan hệ giữa hai thực thể cùng loại: vai trò đệ quy

Quan hệ đệ quy (recursive relationship) là quan hệ mà cùng một loại thực thể tham gia ở nhiều đầu khác nhau. Trong trường hợp này, tên vai trò đặc biệt quan trọng vì tên thực thể không đủ phân biệt hai phía.

### 5.1. Ví dụ nhân viên quản lý nhân viên

Một nhân viên có thể quản lý nhiều nhân viên khác. Mỗi nhân viên có tối đa một quản lý trực tiếp.

Hai vai trò:

- **Người quản lý:** instance ở đầu quản lý.
- **Nhân viên được quản lý:** instance ở đầu báo cáo.

~~~mermaid
flowchart TD
    M["NHÂN VIÊN<br/>Vai trò: người quản lý"] -->|"quản lý<br/>0..* nhân viên"| E["NHÂN VIÊN<br/>Vai trò: người được quản lý"]
    E -->|"báo cáo cho<br/>0..1 người quản lý"| M
~~~

Cấu trúc này có thể được ánh xạ logic bằng một quan hệ EMPLOYEE tự tham chiếu, ví dụ thuộc tính manager_employee_id tham chiếu employee_id. Tên cột cần nêu vai trò để người đọc hiểu đó là mã của người quản lý, không phải mã của một nhân viên bất kỳ.

Các quy tắc cần làm rõ:

- Nhân viên cấp cao nhất có được để trống người quản lý không?
- Có cho phép một nhân viên tự quản lý mình không?
- Có cho phép chu trình như A quản lý B, B quản lý C, C quản lý A không?
- Một nhân viên có thể có nhiều quản lý trực tiếp hay chỉ một?
- Quan hệ quản lý có hiệu lực theo thời gian không?

Khóa ngoại tự tham chiếu bảo đảm người quản lý tồn tại, nhưng không tự ngăn mọi chu trình hoặc bảo đảm một cây tổ chức hợp lệ.

### 5.2. Ví dụ người giới thiệu và người được giới thiệu

Một khách hàng có thể giới thiệu nhiều khách hàng khác tham gia hệ thống. Hai đầu cùng là KHÁCH HÀNG nhưng vai trò khác nhau:

- Người giới thiệu;
- Người được giới thiệu.

Nếu cần lưu thời điểm, chương trình giới thiệu hoặc trạng thái thưởng, quan hệ có thể có thuộc tính riêng hoặc được biểu diễn bằng một thực thể kết hợp. Cần xác định một người có thể được nhiều người giới thiệu hay không, và quy tắc ghi nhận giới thiệu nào có hiệu lực.

## 6. Một loại thực thể tham gia nhiều vai trò trong cùng một quan hệ

Không chỉ quan hệ đệ quy mới cần tên vai trò. Một quan hệ có thể chứa nhiều đầu cùng tham chiếu một loại thực thể.

### 6.1. Địa chỉ thanh toán và địa chỉ giao hàng

Một đơn hàng có thể tham chiếu hai địa chỉ:

- Địa chỉ thanh toán;
- Địa chỉ giao hàng.

Cả hai đầu đều là ĐỊA CHỈ, nhưng vai trò khác nhau. Trong mô hình logic, có thể xuất hiện hai khóa ngoại như billing_address_id và shipping_address_id tham chiếu cùng một quan hệ ADDRESS.

Tên khóa ngoại cần thể hiện vai trò. Nếu đặt cả hai là address_id trong cùng một cấu trúc, người đọc và người bảo trì khó biết giá trị dùng cho mục đích nào.

Cần xác minh thêm:

- Hai vai trò có thể trỏ tới cùng một địa chỉ không?
- Có bắt buộc cả hai địa chỉ không?
- Địa chỉ của đơn có cần giữ nguyên tại thời điểm đặt không?
- Một địa chỉ có thể được dùng bởi nhiều đơn không?

### 6.2. Sân bay khởi hành và sân bay đến

Một chuyến bay liên kết với hai sân bay:

- Sân bay khởi hành;
- Sân bay đến.

Hai đầu cùng là SÂN BAY. Tên vai trò làm rõ thứ tự và hướng của hành trình. Không thể chỉ nói “chuyến bay liên kết sân bay” vì sẽ không biết sân bay nào là điểm đi và sân bay nào là điểm đến.

### 6.3. Tài khoản nguồn và tài khoản đích

Một giao dịch chuyển tiền liên kết hai tài khoản:

- Tài khoản nguồn;
- Tài khoản đích.

Cả hai là TÀI KHOẢN, nhưng mỗi vai trò có quy tắc khác nhau. Ví dụ tài khoản nguồn phải đủ điều kiện ghi nợ; tài khoản đích phải đủ điều kiện nhận tiền. Một quy tắc kiểm tra như hai tài khoản không được giống nhau có thể áp dụng trên cả hai vai trò.

## 7. Quan hệ đối xứng và không đối xứng

Một số quan hệ có ý nghĩa như nhau khi đổi vị trí hai đầu; một số khác có hướng rõ ràng.

### 7.1. Quan hệ đối xứng

Ví dụ quan hệ “là bạn của” giữa hai người. Nếu A là bạn của B thì B cũng là bạn của A theo định nghĩa đối xứng.

Hai đầu có cùng loại thực thể và vai trò về ngữ nghĩa gần như giống nhau. Tuy nhiên, hệ thống vẫn cần quy tắc lưu trữ để tránh lưu hai lần cùng một cặp A-B và B-A nếu quan hệ không có hướng.

Cần xác định:

- Quan hệ có thật sự đối xứng không?
- Có cho phép một người là bạn của chính mình không?
- Quan hệ có cần trạng thái chấp nhận hay chờ xác nhận không?
- Có cần lưu ai khởi tạo lời mời không?

Một lời mời kết bạn có hướng theo vai trò người gửi và người nhận; mối quan hệ bạn bè sau khi chấp nhận có thể là đối xứng. Đây là hai khái niệm khác nhau dù cùng liên quan đến hai người.

### 7.2. Quan hệ không đối xứng

Các quan hệ “quản lý”, “giới thiệu”, “chuyển tiền từ”, “gửi đến” có hướng. Đổi hai đầu sẽ thay đổi ý nghĩa.

Ví dụ A chuyển tiền cho B không tương đương B chuyển tiền cho A. Tên vai trò phải phân biệt nguồn và đích.

Không nên dùng một cấu trúc quan hệ không hướng cho nghiệp vụ có hướng mà không lưu thông tin phân biệt hai đầu.

### 7.3. Quan hệ phản xạ, đối xứng và bắc cầu

Khi nghiệp vụ có quy tắc quan hệ phức tạp, có thể cần xác định các tính chất:

- **Phản xạ:** một đối tượng có quan hệ với chính nó hay không.
- **Đối xứng:** nếu A liên hệ B thì B có liên hệ A không.
- **Bắc cầu:** nếu A liên hệ B và B liên hệ C thì có suy ra A liên hệ C không.

Ví dụ “bằng nhau” có tính phản xạ, đối xứng và bắc cầu; “quản lý trực tiếp” thường không có các tính chất đó. Không nên suy diễn quan hệ bắc cầu nếu nghiệp vụ chỉ xác nhận quan hệ trực tiếp.

## 8. Vai trò trong quan hệ nhiều ngôi

Quan hệ nhiều ngôi liên kết từ ba loại thực thể trở lên. Mỗi đầu cần có vai trò riêng, vì chỉ liệt kê tên các loại thực thể có thể chưa diễn đạt đầy đủ ý nghĩa.

Ví dụ:

> Nhà cung cấp cung cấp một sản phẩm cho một kho theo một thỏa thuận cụ thể.

Các vai trò:

- Nhà cung cấp: bên cung ứng;
- Sản phẩm: mặt hàng được cung ứng;
- Kho: nơi nhận hàng.

~~~mermaid
flowchart TD
    R["NHÀ CUNG CẤP<br/>Vai trò: bên cung ứng"]
    P["SẢN PHẨM<br/>Vai trò: mặt hàng"]
    W["KHO<br/>Vai trò: nơi nhận"]
    X(("CUNG ỨNG"))
    R --> X
    P --> X
    W --> X
~~~

Nếu chỉ tách thành ba quan hệ đôi “nhà cung cấp cung cấp sản phẩm”, “nhà cung cấp giao cho kho” và “kho lưu sản phẩm”, mô hình có thể không bảo toàn ý nghĩa của một thỏa thuận cung ứng cụ thể. Ví dụ, giá cung ứng có thể phụ thuộc đồng thời vào nhà cung cấp, sản phẩm, kho và thời hạn hợp đồng.

Vai trò của từng đầu phải được ghi rõ. Nếu quan hệ có thuộc tính riêng hoặc cần định danh, có thể chuyển thành thực thể kết hợp như THỎA THUẬN CUNG ỨNG.

## 9. Vai trò khi quan hệ được chuyển thành mô hình logic

Khi chuyển sang mô hình logic quan hệ, tên vai trò thường ảnh hưởng trực tiếp đến tên khóa ngoại, tên thuộc tính và tên quan hệ kết hợp.

### 9.1. Hai khóa ngoại cùng tham chiếu một bảng

Ví dụ, bảng ORDER có thể tham chiếu CUSTOMER ở hai vai trò:

| Thuộc tính logic | Vai trò | Tham chiếu |
|---|---|---|
| placed_by_customer_id | Khách hàng đặt đơn | CUSTOMER.customer_id |
| billed_to_customer_id | Khách hàng nhận trách nhiệm thanh toán | CUSTOMER.customer_id |

Nếu hai vai trò có thể là cùng một khách hàng, cả hai khóa ngoại có thể mang cùng giá trị. Nếu nghiệp vụ yêu cầu khác nhau trong một số trường hợp, cần ghi rõ ràng buộc đó.

Tên cột như customer_id_1 và customer_id_2 không diễn đạt ý nghĩa. Hãy dùng tên theo vai trò để tránh phụ thuộc vào thứ tự khai báo.

### 9.2. Quan hệ đệ quy

Bảng EMPLOYEE có thể có manager_employee_id tham chiếu employee_id của cùng bảng. Tên manager làm rõ vai trò ở đầu tham chiếu. Nếu mô hình cần lưu nhiều cấp quản lý hoặc lịch sử điều chuyển, một bảng quan hệ quản lý có thể phù hợp hơn.

### 9.3. Quan hệ kết hợp

Với quan hệ nhiều-nhiều có vai trò rõ, bảng kết hợp cần đặt tên thể hiện hành động hoặc ý nghĩa, ví dụ ENROLLMENT cho việc sinh viên đăng ký học phần.

Các thuộc tính có thể gồm:

- student_id: vai trò sinh viên đăng ký;
- course_id: vai trò học phần được đăng ký;
- enrolled_at: thời điểm đăng ký;
- enrollment_status: trạng thái đăng ký.

Nếu một sinh viên có thể đăng ký cùng học phần nhiều lần qua các kỳ khác nhau, khóa duy nhất không thể chỉ là cặp student_id và course_id. Cần thêm kỳ học hoặc một định danh lần đăng ký để bảo toàn nghiệp vụ.

## 10. Quy tắc đặt tên nhất quán trong mô hình

Một quy ước tốt giúp người đọc hiểu mô hình mà không cần mở tài liệu giải thích cho từng đường nối.

### 10.1. Quy tắc cho tên quan hệ

- Dùng động từ hoặc cụm động từ mô tả hành động hay ý nghĩa.
- Ưu tiên cách gọi nghiệp vụ đã được xác nhận.
- Tránh tên chung chung nếu có thể dùng từ cụ thể hơn.
- Dùng một tên chuẩn cho cùng một ý nghĩa.
- Nếu có nhiều quan hệ giữa cùng hai thực thể, đặt tên riêng để phân biệt.

### 10.2. Quy tắc cho tên vai trò

- Dùng danh từ hoặc cụm danh từ chỉ vị trí tham gia.
- Tên phải phân biệt được các đầu, đặc biệt khi cùng loại thực thể xuất hiện nhiều lần.
- Tránh dùng “bên 1”, “bên 2”, “đối tượng A”, “đối tượng B” trong mô hình đã chốt.
- Không dùng tên vai trò như thể đó luôn là một loại thực thể độc lập.
- Nếu vai trò có điều kiện hoặc thời hạn, ghi rõ phạm vi và thời gian áp dụng.

### 10.3. Quy tắc cho tên khóa ngoại

Tên khóa ngoại nên phản ánh vai trò của thực thể được tham chiếu. Ví dụ:

| Không rõ nghĩa | Rõ nghĩa hơn |
|---|---|
| customer_id_1 | placed_by_customer_id |
| customer_id_2 | billed_to_customer_id |
| employee_id_1 | manager_employee_id |
| employee_id_2 | approved_by_employee_id |
| address_id_1 | billing_address_id |
| address_id_2 | shipping_address_id |

Tên vật lý có thể theo quy ước snake_case hoặc camelCase của dự án, nhưng ý nghĩa vai trò cần được giữ nguyên.

### 10.4. Dùng tên chuẩn và bí danh

Nếu bộ phận kinh doanh gọi “người mua”, còn bộ phận chăm sóc gọi “chủ tài khoản”, hãy xác định đó có phải cùng một khái niệm và vai trò không. Nếu là bí danh, ghi nhận để truy vết. Nếu khác vai trò, phải giữ tên riêng.

## 11. Ví dụ tổng hợp: mô hình đơn hàng có nhiều vai trò

Một hệ thống bán hàng có yêu cầu:

- Một khách hàng có thể đặt nhiều đơn hàng.
- Mỗi đơn được đặt bởi một khách hàng.
- Đơn có thể được thanh toán bởi một khách hàng hoặc tổ chức khác với người đặt.
- Đơn có địa chỉ thanh toán và địa chỉ giao hàng.
- Nhân viên có thể phê duyệt đơn trong một số trường hợp.
- Mỗi đơn có thể có nhiều kiện giao.

Ta có thể mô tả vai trò như sau:

| Quan hệ | Đầu thứ nhất và vai trò | Đầu thứ hai và vai trò | Ý nghĩa |
|---|---|---|---|
| ĐẶT ĐƠN | KHÁCH HÀNG — người đặt | ĐƠN HÀNG — đơn được đặt | Ai tạo đơn? |
| CHỊU TRÁCH NHIỆM THANH TOÁN | KHÁCH HÀNG/TỔ CHỨC — bên thanh toán | ĐƠN HÀNG — đơn được thanh toán | Ai chịu trách nhiệm thanh toán? |
| DÙNG ĐỊA CHỈ THANH TOÁN | ĐƠN HÀNG — đơn cần lập hóa đơn | ĐỊA CHỈ — địa chỉ thanh toán | Hóa đơn dùng địa chỉ nào? |
| DÙNG ĐỊA CHỈ GIAO HÀNG | ĐƠN HÀNG — đơn cần giao | ĐỊA CHỈ — địa chỉ nhận hàng | Hàng được giao đến đâu? |
| PHÊ DUYỆT | NHÂN VIÊN — người phê duyệt | ĐƠN HÀNG — đơn được phê duyệt | Ai có quyền phê duyệt? |
| GỬI THÀNH KIỆN | ĐƠN HÀNG — đơn cần giao | KIỆN HÀNG — kiện thuộc đơn | Đơn được giao thành những kiện nào? |

Sơ đồ minh họa:

~~~mermaid
flowchart LR
    C["KHÁCH HÀNG<br/>người đặt"] -->|"đặt"| O["ĐƠN HÀNG"]
    P["KHÁCH HÀNG / TỔ CHỨC<br/>bên thanh toán"] -->|"thanh toán cho"| O
    E["NHÂN VIÊN<br/>người phê duyệt"] -->|"phê duyệt"| O
    O -->|"dùng địa chỉ thanh toán"| BA["ĐỊA CHỈ<br/>billing"]
    O -->|"dùng địa chỉ giao hàng"| SA["ĐỊA CHỈ<br/>shipping"]
    O -->|"được gửi thành"| S["KIỆN HÀNG"]
~~~

Điểm cần chú ý:

- Người đặt và bên thanh toán có thể là cùng một chủ thể hoặc khác nhau.
- Địa chỉ thanh toán và địa chỉ giao hàng có thể trùng hoặc khác.
- Người phê duyệt là một vai trò của nhân viên trong quan hệ phê duyệt, không nhất thiết là một loại nhân viên mới.
- Một đơn có thể được giao thành nhiều kiện; mỗi kiện cần có định danh và trạng thái riêng nếu nghiệp vụ yêu cầu theo dõi.

Tên vai trò cho phép mô hình biểu diễn các trường hợp này mà không nhập nhằng các khóa tham chiếu.

## 12. Những lỗi thường gặp

1. **Chỉ ghi tên hai thực thể:** người đọc biết có liên kết nhưng không hiểu vai trò của từng bên.
2. **Dùng tên quan hệ quá chung:** “có”, “liên quan”, “kết nối” không nói rõ hành động hoặc quy tắc.
3. **Không phân biệt hai đầu cùng loại thực thể:** quan hệ NHÂN VIÊN quản lý NHÂN VIÊN cần vai trò người quản lý và người được quản lý.
4. **Nhầm vai trò với loại thực thể:** “người phê duyệt” có thể là vai trò của nhân viên, không phải luôn là một bảng riêng.
5. **Nhầm tên vai trò với bội số:** tên “người đặt” không cho biết một khách hàng được đặt bao nhiêu đơn.
6. **Chỉ đọc quan hệ theo một chiều:** sơ đồ dễ bị đảo chủ thể và đối tượng.
7. **Dùng tên khóa ngoại theo số thứ tự:** customer_id_1 và customer_id_2 không thể hiện mục đích.
8. **Giả định quan hệ đối xứng:** “bạn của” có thể đối xứng nhưng “quản lý” hoặc “chuyển tiền cho” thì không.
9. **Tách quan hệ nhiều ngôi thành các cặp không tương đương:** làm mất ý nghĩa của tổ hợp các vai trò.
10. **Bỏ qua vai trò có thời hạn:** người quản lý hoặc địa chỉ sử dụng có thể thay đổi theo thời gian.
11. **Dùng nhiều tên cho cùng một ý nghĩa:** gây khó khăn khi truy vết và trao đổi giữa nhóm.
12. **Không kiểm tra các trường hợp ngoại lệ:** mô hình có thể đúng với trường hợp đơn giản nhưng sai khi người đặt khác người thanh toán hoặc đơn giao nhiều kiện.

## 13. Checklist kiểm tra tên quan hệ và vai trò

- [ ] Mỗi quan hệ có tên thể hiện rõ hành động hoặc ý nghĩa nghiệp vụ.
- [ ] Mỗi đầu quan hệ có loại thực thể và vai trò được xác định.
- [ ] Có thể đọc quan hệ thành câu có nghĩa từ cả hai phía.
- [ ] Nếu cùng loại thực thể tham gia nhiều đầu, tên vai trò phân biệt được các đầu.
- [ ] Bội số tối thiểu và tối đa được xác định độc lập với tên vai trò.
- [ ] Tính tham gia bắt buộc hoặc tùy chọn được xác nhận.
- [ ] Quan hệ đệ quy có tên vai trò rõ và quy tắc chống vòng lặp nếu cần.
- [ ] Quan hệ đối xứng và không đối xứng được phân biệt.
- [ ] Quan hệ nhiều ngôi có tên và vai trò cho từng thành phần.
- [ ] Tên khóa ngoại phản ánh vai trò, không dùng số thứ tự khó hiểu.
- [ ] Vai trò không bị nhầm với loại thực thể hoặc thuộc tính.
- [ ] Tên chuẩn được dùng nhất quán trong sơ đồ, từ điển dữ liệu và tài liệu.

## 14. Bài tập thực hành

Một hệ thống quản lý nhân sự có các yêu cầu:

- Một nhân viên có thể quản lý nhiều nhân viên.
- Mỗi nhân viên có tối đa một quản lý trực tiếp.
- Nhân viên có thể gửi yêu cầu nghỉ phép.
- Một nhân viên khác có quyền phê duyệt yêu cầu.
- Một yêu cầu nghỉ phép thuộc về đúng một nhân viên gửi.
- Một yêu cầu có thể chưa được phê duyệt, đang chờ hoặc đã có kết quả.

Hãy thực hiện:

1. Xác định các loại thực thể tham gia.
2. Đặt tên quan hệ giữa nhân viên quản lý và nhân viên được quản lý.
3. Đặt tên vai trò ở hai đầu của quan hệ gửi yêu cầu.
4. Đặt tên vai trò ở hai đầu của quan hệ phê duyệt.
5. Nêu bội số tối thiểu và tối đa theo yêu cầu.
6. Đề xuất tên khóa ngoại nếu ánh xạ sang mô hình logic quan hệ.
7. Chỉ ra quy tắc nào cần xử lý ngoài khóa ngoại thông thường.

**Gợi ý đáp án:**

| Quan hệ | Vai trò đầu thứ nhất | Vai trò đầu thứ hai | Bội số tham khảo |
|---|---|---|---|
| QUẢN LÝ | Nhân viên quản lý | Nhân viên được quản lý | Một quản lý có 0..* nhân viên; một nhân viên có 0..1 quản lý trực tiếp |
| GỬI YÊU CẦU | Người gửi yêu cầu | Yêu cầu nghỉ phép được gửi | Một nhân viên gửi 0..* yêu cầu; mỗi yêu cầu thuộc đúng 1 nhân viên |
| PHÊ DUYỆT | Người phê duyệt | Yêu cầu được phê duyệt | Một nhân viên có thể phê duyệt 0..* yêu cầu; một yêu cầu có thể chưa có người phê duyệt hoặc có tối đa 1 người theo quy trình giả định |

Tên thuộc tính logic tham khảo:

- EMPLOYEE.manager_employee_id: người quản lý trực tiếp.
- LEAVE_REQUEST.requested_by_employee_id: nhân viên gửi yêu cầu.
- LEAVE_REQUEST.approved_by_employee_id: nhân viên phê duyệt, có thể để trống khi chưa xử lý.

Khóa ngoại có thể bảo đảm người quản lý, người gửi và người phê duyệt tồn tại. Các quy tắc như người gửi không được tự phê duyệt, người phê duyệt phải có quyền tại thời điểm phê duyệt, ngày nghỉ không trùng lịch cấm và không tạo chu trình quản lý cần cơ chế kiểm tra nghiệp vụ phù hợp.

Bài tập đạt yêu cầu khi người đọc có thể xác định rõ ai quản lý ai, ai gửi yêu cầu, ai phê duyệt và một yêu cầu đang ở trạng thái nào mà không cần suy đoán từ tên cột hoặc vị trí hai đầu quan hệ.
