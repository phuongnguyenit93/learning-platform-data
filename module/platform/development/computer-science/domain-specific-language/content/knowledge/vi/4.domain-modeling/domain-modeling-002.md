# Quan hệ giữa các khái niệm

Mô hình miền (domain model) mô tả những khái niệm quan trọng trong một lĩnh vực và cách chúng liên hệ với nhau. Trong một hệ thống thương mại điện tử, các khái niệm có thể gồm Khách hàng, Đơn hàng, Sản phẩm và Thanh toán. Chỉ liệt kê các khái niệm này là chưa đủ: cần biết khách hàng đặt đơn hàng như thế nào, đơn hàng gồm những dòng hàng nào, mỗi dòng hàng tham chiếu sản phẩm nào và thanh toán gắn với đơn hàng ra sao.

**Quan hệ giữa các khái niệm** diễn đạt những liên kết có ý nghĩa trong miền bài toán. Chúng cho biết một đối tượng có liên quan đến đối tượng nào, vai trò của mỗi bên, số lượng liên kết được phép, điều kiện phải thỏa mãn và đôi khi cả vòng đời của các đối tượng liên quan.

Trong thiết kế ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), mô hình quan hệ là nền tảng để xác định từ vựng và ngữ nghĩa. DSL cần cho phép người dùng mô tả những quan hệ có ý nghĩa đối với miền, đồng thời giúp bộ phân tích và bộ thực thi hiểu được các ràng buộc đó.

## 1. Vì sao cần mô hình hóa quan hệ?

Một mô hình chỉ có các khái niệm riêng lẻ giống như danh sách các danh từ. Quan hệ kết nối chúng thành một mô tả có ý nghĩa về lĩnh vực.

Ví dụ, trong hệ thống bán hàng:

- Khách hàng **đặt** đơn hàng.
- Đơn hàng **bao gồm** các dòng hàng.
- Mỗi dòng hàng **chỉ đến** một sản phẩm.
- Đơn hàng **được thanh toán bằng** một hoặc nhiều giao dịch thanh toán, tùy chính sách.
- Nhân viên **xử lý** đơn hàng.

Các động từ như “đặt”, “bao gồm”, “chỉ đến”, “thanh toán bằng” và “xử lý” thể hiện ngữ nghĩa khác nhau. Nếu chỉ vẽ một đường nối giữa các khái niệm mà không giải thích ý nghĩa, người đọc khó biết liên kết đó biểu thị điều gì.

Mô hình hóa quan hệ giúp:

1. Làm rõ cách các đối tượng trong miền tương tác và phụ thuộc lẫn nhau.
2. Xác định số lượng và vai trò của các đối tượng tham gia.
3. Biểu diễn các quy tắc nghiệp vụ mà hệ thống cần bảo vệ.
4. Làm cơ sở thiết kế cấu trúc dữ liệu, API, lớp và hành vi.
5. Giúp DSL có cú pháp và ngữ nghĩa nhất quán khi diễn đạt các liên kết.

Quan hệ cần xuất phát từ hiểu biết về nghiệp vụ. Không nên thêm một quan hệ chỉ vì hai bảng có thể nối với nhau hoặc vì một lớp có thể giữ tham chiếu đến lớp khác.

## 2. Thành phần của một quan hệ

Khi mô tả một quan hệ, cần xác định ít nhất ý nghĩa, các bên tham gia và vai trò của từng bên. Tùy miền, có thể cần thêm lực lượng (multiplicity), hướng truy cập, điều kiện và vòng đời.

### 2.1. Các khái niệm tham gia

Một quan hệ liên kết hai hoặc nhiều khái niệm. Ví dụ, quan hệ “đặt” liên kết Khách hàng với Đơn hàng.

Trong mô hình hướng đối tượng hoặc UML, các khái niệm thường được biểu diễn bằng lớp. Trong mô hình miền, chúng có thể được gọi là thực thể (entity), đối tượng giá trị (value object), tác nhân, tài nguyên hoặc khái niệm nghiệp vụ. Tên gọi phụ thuộc vào phương pháp mô hình hóa đang dùng.

### 2.2. Tên quan hệ và vai trò

Tên quan hệ nên diễn đạt được ý nghĩa nghiệp vụ, thường dùng động từ hoặc cụm động từ.

Ví dụ:

- Khách hàng **đặt** Đơn hàng.
- Đơn hàng **thuộc về** Khách hàng.
- Đơn hàng **chứa** Dòng hàng.
- Dòng hàng **tham chiếu** Sản phẩm.

Hai cách diễn đạt “Khách hàng đặt Đơn hàng” và “Đơn hàng thuộc về Khách hàng” có thể mô tả cùng một liên kết khi nhìn từ hai phía. Tuy nhiên, tên vai trò giúp làm rõ vị trí của mỗi bên trong quan hệ.

Một quan hệ giữa hai lớp có thể có tên vai trò ở cả hai đầu. Với quan hệ giữa Nhân viên và Phòng ban, vai trò ở phía Nhân viên có thể là “thành viên”, còn phía Phòng ban là “đơn vị quản lý”. Vai trò rất hữu ích khi một lớp có nhiều quan hệ đến cùng một lớp khác.

Tên mơ hồ như “có”, “liên quan” hoặc “sử dụng” đôi khi cần được thay bằng động từ cụ thể hơn. Chẳng hạn “Đơn hàng có Sản phẩm” không cho biết sản phẩm được tham chiếu trực tiếp hay thông qua dòng hàng, và một đơn hàng có thể chứa cùng một sản phẩm nhiều lần hay không.

### 2.3. Số lượng liên kết (multiplicity)

Multiplicity cho biết một đối tượng có thể hoặc phải liên kết với bao nhiêu đối tượng ở đầu kia của quan hệ.

Các ký hiệu thường dùng trong UML:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `1` | Chính xác một |
| `0..1` | Không có hoặc có một |
| `0..*` | Không có hoặc có nhiều |
| `1..*` | Ít nhất một |
| `2..5` | Từ hai đến năm |
| `*` | Nhiều; thường được hiểu là `0..*` |

Ví dụ, mỗi Đơn hàng phải thuộc về đúng một Khách hàng, còn một Khách hàng có thể chưa đặt đơn hàng nào hoặc đã đặt nhiều đơn hàng. Ta mô tả:

- Tại đầu Khách hàng: `1` — mỗi Đơn hàng liên kết với đúng một Khách hàng.
- Tại đầu Đơn hàng: `0..*` — mỗi Khách hàng có thể liên kết với không, một hoặc nhiều Đơn hàng.

Điểm cần nhớ: trong UML, con số đặt gần một đầu quan hệ mô tả số lượng đối tượng ở đầu đó có thể liên kết với một đối tượng ở đầu đối diện.

Một quan hệ khác là Đơn hàng và Dòng hàng. Mỗi Dòng hàng thuộc đúng một Đơn hàng; một Đơn hàng hợp lệ có thể cần ít nhất một Dòng hàng. Khi đó, phía Đơn hàng có multiplicity `1`, phía Dòng hàng có thể là `1..*`. Nếu hệ thống cho phép đơn hàng nháp chưa có dòng hàng, mô hình cần phản ánh trạng thái đó, ví dụ cho phép `0..*` trong giai đoạn nháp và áp dụng quy tắc tối thiểu một dòng khi xác nhận.

Multiplicity biểu đạt giới hạn số lượng, nhưng không phải lúc nào cũng đủ để mô tả toàn bộ nghiệp vụ. Nó không tự nói rằng một đơn hàng phải được xác nhận trước khi thanh toán, hoặc một khách hàng chỉ được đặt đơn khi tài khoản đang hoạt động. Những điều kiện đó cần được mô tả bằng ràng buộc hoặc quy tắc nghiệp vụ riêng.

### 2.4. Hướng của quan hệ và khả năng truy cập

Một quan hệ có thể được mô hình hóa theo một chiều hoặc hai chiều.

- **Một chiều (unidirectional):** từ một khái niệm có thể truy cập khái niệm còn lại theo hướng đã định nghĩa.
- **Hai chiều (bidirectional):** mô hình cho phép đi từ cả hai phía.

Ví dụ, Đơn hàng giữ tham chiếu đến Khách hàng để biết người đặt hàng. Nếu Khách hàng không cần duyệt toàn bộ đơn hàng của mình qua mô hình đối tượng, quan hệ có thể chỉ cần điều hướng từ Đơn hàng đến Khách hàng. Nếu màn hình hồ sơ khách hàng cần liệt kê các đơn hàng, ứng dụng có thể cung cấp thao tác truy vấn riêng hoặc mô hình hóa điều hướng ngược.

Hướng truy cập trong mô hình không nhất thiết thay đổi ý nghĩa nghiệp vụ. Việc một lớp có thể truy cập lớp kia là quyết định thiết kế phần mềm; quan hệ “khách hàng đặt đơn hàng” vẫn có ý nghĩa ngay cả khi mã nguồn chỉ giữ tham chiếu theo một chiều.

Với quan hệ hai chiều trong mã hướng đối tượng, cần duy trì tính nhất quán giữa hai phía. Nếu một phía được thêm hoặc xóa mà phía còn lại không được cập nhật, mô hình trong bộ nhớ có thể rơi vào trạng thái mâu thuẫn. Có thể giải quyết bằng phương thức nghiệp vụ điều phối thay đổi, cơ chế đồng bộ hoặc chỉ chọn một phía làm nguồn quản lý.

## 3. Những loại quan hệ thường gặp

Trong mô hình miền và mô hình lớp, có một số dạng quan hệ phổ biến. Các thuật ngữ có thể khác nhau giữa UML, thiết kế hướng đối tượng và phương pháp phân tích miền, vì vậy cần đọc theo ngữ nghĩa mà mô hình đang sử dụng.

### 3.1. Liên kết (association)

Association là quan hệ cấu trúc cho biết các đối tượng có liên hệ với nhau trong miền.

Ví dụ, Nhân viên làm việc tại Phòng ban. Mỗi Nhân viên thuộc một Phòng ban, còn một Phòng ban có nhiều Nhân viên. Quan hệ này có thể có multiplicity một-nhiều.

Association thường trả lời câu hỏi: “Đối tượng này có liên hệ với đối tượng nào và trong vai trò gì?”

Liên kết có thể tồn tại lâu dài hoặc chỉ trong một khoảng thời gian. Nếu nhân viên chuyển phòng ban, mô hình có thể chỉ lưu phòng ban hiện tại, hoặc cần lưu cả lịch sử phân công. Quyết định này phụ thuộc yêu cầu nghiệp vụ.

### 3.2. Kết tập (aggregation)

Aggregation là dạng liên kết toàn thể - bộ phận (whole-part) với ý nghĩa sở hữu hoặc tập hợp tương đối yếu. Bộ phận vẫn có thể tồn tại độc lập với toàn thể hoặc được chia sẻ tùy mô hình.

Ví dụ, một Nhóm dự án tập hợp nhiều Nhân viên. Nhân viên vẫn tồn tại khi nhóm dự án giải thể và có thể tham gia nhóm khác.

Trong UML, aggregation thường được biểu diễn bằng hình thoi rỗng ở phía toàn thể. Tuy nhiên, ngữ nghĩa của shared aggregation trong UML khá yếu và không tự xác định đầy đủ vòng đời hay quy tắc chia sẻ. Vì vậy, tài liệu miền cần giải thích rõ ý định thay vì chỉ dựa vào ký hiệu.

### 3.3. Hợp thành (composition)

Composition là dạng toàn thể - bộ phận có ràng buộc sở hữu mạnh hơn. Bộ phận thuộc về một toàn thể trong phạm vi mô hình và vòng đời của nó thường phụ thuộc vào toàn thể đó.

Ví dụ, Dòng hàng là một phần của Đơn hàng. Nếu xóa một Đơn hàng theo mô hình nghiệp vụ, các Dòng hàng của nó thường cũng bị loại bỏ hoặc chuyển sang trạng thái lưu trữ tương ứng. Dòng hàng không có ý nghĩa độc lập như một Sản phẩm.

Trong UML, composition thường dùng hình thoi đặc ở phía toàn thể. Một bộ phận trong composition thường thuộc về tối đa một toàn thể tại một thời điểm.

Composition là quyết định ngữ nghĩa về sở hữu và vòng đời. Không nên dùng nó chỉ vì một đối tượng được lưu trong bảng có khóa ngoại đến đối tượng khác. Ví dụ, Sản phẩm được một Dòng hàng tham chiếu nhưng vẫn tồn tại độc lập với Đơn hàng; vì vậy, quan hệ Dòng hàng - Sản phẩm thường là association, không phải composition.

### 3.4. Khái quát hóa và chuyên biệt hóa (generalization/specialization)

Generalization mô tả quan hệ “là một loại của” (is-a). Một khái niệm tổng quát có các biến thể chuyên biệt kế thừa hoặc mở rộng đặc điểm chung.

Ví dụ:

- Phương tiện là khái niệm tổng quát.
- Ô tô và Xe máy là các loại phương tiện.
- Mỗi Ô tô là một Phương tiện; mỗi Xe máy cũng là một Phương tiện.

Trong UML, generalization thường được biểu diễn bằng đường nối có mũi tên tam giác rỗng hướng về lớp tổng quát.

Không nên nhầm generalization với association. “Ô tô là Phương tiện” là quan hệ phân loại; “Ô tô được đăng ký bởi Chủ sở hữu” là association. Dùng kế thừa chỉ vì hai lớp có vài thuộc tính giống nhau có thể tạo ra hệ thống phân cấp không phản ánh đúng miền. Cần kiểm tra quan hệ thay thế: đối tượng của lớp con có thể được dùng ở nơi yêu cầu lớp cha mà vẫn giữ đúng ý nghĩa hay không.

### 3.5. Phụ thuộc (dependency)

Dependency mô tả việc một phần tử cần hoặc sử dụng phần tử khác để thực hiện một nhiệm vụ. Nó thường biểu thị sự phụ thuộc về sử dụng hoặc thiết kế, không nhất thiết là một liên kết cấu trúc lâu dài giữa các đối tượng miền.

Ví dụ, Dịch vụ lập hóa đơn sử dụng Bộ định dạng tiền tệ để tạo nội dung hóa đơn. Dịch vụ lập hóa đơn phụ thuộc vào khả năng định dạng, nhưng không nhất thiết sở hữu hoặc lưu một Bộ định dạng tiền tệ như một phần dữ liệu miền.

Trong UML, dependency thường được biểu diễn bằng đường nét đứt có mũi tên. Trong mã nguồn, dependency có thể xuất hiện qua tham số hàm, lời gọi phương thức hoặc thành phần được tiêm vào đối tượng.

### 3.6. So sánh các loại quan hệ

| Loại quan hệ | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| Association | Các đối tượng có liên hệ trong miền | Khách hàng đặt Đơn hàng |
| Aggregation | Toàn thể tập hợp các bộ phận có thể tồn tại độc lập | Nhóm dự án tập hợp Nhân viên |
| Composition | Toàn thể sở hữu bộ phận với ràng buộc vòng đời mạnh | Đơn hàng gồm các Dòng hàng |
| Generalization | Quan hệ phân loại “là một loại của” | Ô tô là Phương tiện |
| Dependency | Một phần tử sử dụng hoặc phụ thuộc vào phần tử khác | Dịch vụ hóa đơn dùng Bộ định dạng |

Các loại quan hệ không phải một danh sách đầy đủ cho mọi phương pháp mô hình hóa. Một miền có thể cần các khái niệm như kế thừa vai trò, liên kết có thời hạn, quan hệ nhân quả hoặc quan hệ giữa các sự kiện. Hãy dùng thuật ngữ phù hợp với phương pháp đang áp dụng và định nghĩa rõ ý nghĩa trong tài liệu.

## 4. Các kiểu lực lượng giữa hai khái niệm

Multiplicity thường dẫn đến bốn dạng quan hệ cơ bản khi mô hình hóa dữ liệu hoặc đối tượng.

### 4.1. Một - một (one-to-one)

Một đối tượng ở phía này liên kết với tối đa hoặc chính xác một đối tượng ở phía kia, và ngược lại.

Ví dụ: mỗi Hồ sơ cá nhân gắn với một Tài khoản đăng nhập và mỗi Tài khoản đăng nhập gắn với một Hồ sơ cá nhân. Nếu cả hai phía đều bắt buộc, multiplicity là `1` ở cả hai đầu. Nếu một hồ sơ có thể chưa có tài khoản, đầu tài khoản có thể là `0..1`.

Không phải mọi cặp một - một đều cần tách thành hai khái niệm. Nếu hai khái niệm luôn có cùng vòng đời và không có lý do nghiệp vụ để tách, có thể chúng thuộc cùng một khái niệm hoặc cùng một cấu trúc. Việc tách có thể hữu ích khi quyền truy cập, bảo mật hoặc vòng đời khác nhau.

### 4.2. Một - nhiều (one-to-many)

Một đối tượng ở phía thứ nhất liên kết với nhiều đối tượng ở phía thứ hai, trong khi mỗi đối tượng phía thứ hai liên kết với một đối tượng phía thứ nhất.

Ví dụ: một Khách hàng đặt nhiều Đơn hàng; mỗi Đơn hàng thuộc về một Khách hàng.

Trong cơ sở dữ liệu quan hệ, khóa ngoại thường được đặt ở bảng phía nhiều để tham chiếu bảng phía một. Tuy nhiên, cách lưu trữ là chi tiết triển khai; ý nghĩa nghiệp vụ cần được xác định trước.

### 4.3. Nhiều - một (many-to-one)

Đây là cùng một quan hệ một - nhiều khi nhìn từ phía đối tượng ở đầu nhiều.

Ví dụ: nhiều Đơn hàng thuộc về một Khách hàng. Trong mô hình đối tượng, mỗi Đơn hàng có thể giữ tham chiếu đến một Khách hàng.

Khi đọc mô hình, cần xem multiplicity ở cả hai đầu thay vì chỉ dựa vào tên “một - nhiều” hoặc “nhiều - một”.

### 4.4. Nhiều - nhiều (many-to-many)

Nhiều đối tượng ở mỗi phía có thể liên kết với nhiều đối tượng ở phía còn lại.

Ví dụ: Sinh viên đăng ký nhiều Môn học, và một Môn học có nhiều Sinh viên đăng ký. Đây là quan hệ nhiều - nhiều.

Trong cơ sở dữ liệu quan hệ, quan hệ này thường được triển khai bằng bảng liên kết. Trong mô hình miền, nếu việc đăng ký có thuộc tính như ngày đăng ký, trạng thái, điểm số hoặc người duyệt, nên xem xét tạo khái niệm riêng là Đăng ký thay vì giữ một liên kết không có dữ liệu.

## 5. Quan hệ có thể mang dữ liệu và quy tắc riêng

Một quan hệ ban đầu có thể chỉ là liên kết đơn giản. Khi nghiệp vụ cần lưu thuộc tính của chính liên kết, nên mô hình hóa nó như một khái niệm riêng, thường gọi là association class, association entity hoặc thực thể liên kết tùy phương pháp.

Ví dụ, Sinh viên và Môn học có quan hệ nhiều - nhiều. Nhưng lần đăng ký cụ thể có các thông tin:

- Ngày đăng ký.
- Học kỳ.
- Trạng thái đăng ký.
- Điểm tổng kết.
- Người phê duyệt.

Các thuộc tính này không thuộc riêng Sinh viên và cũng không thuộc riêng Môn học. Chúng mô tả một lần Đăng ký.

Mô hình có thể được biểu diễn:

~~~text
Student 1 ---- 0..* Enrollment 0..* ---- 1 Course

Enrollment
  - enrolledAt
  - semester
  - status
  - finalGrade
~~~

Mỗi Đăng ký gắn với đúng một Sinh viên và một Môn học; một Sinh viên có nhiều Đăng ký; một Môn học có nhiều Đăng ký. Quan hệ nhiều - nhiều ban đầu được tách thành hai quan hệ một - nhiều thông qua khái niệm Đăng ký.

Tương tự, trong thương mại điện tử, Đơn hàng và Sản phẩm có thể được liên kết thông qua Dòng hàng. Dòng hàng lưu số lượng, đơn giá tại thời điểm mua, mức giảm giá và các thông tin khác. Việc tạo khái niệm Dòng hàng giúp giữ đúng ngữ nghĩa lịch sử: giá sản phẩm hiện tại có thể thay đổi, nhưng đơn giá của một đơn hàng đã xác nhận cần được lưu theo thời điểm giao dịch.

## 6. Biểu diễn quan hệ trong DSL

Một DSL mô hình miền cần có cách biểu diễn quan hệ dễ đọc, không mơ hồ và có thể kiểm tra. Cú pháp cụ thể tùy ngôn ngữ; ví dụ dưới đây là một DSL giả định nhằm minh họa ý tưởng, không phải cú pháp chuẩn của một công cụ cụ thể.

~~~text
entity Customer {
  id: CustomerId
  name: String
}

entity Order {
  id: OrderId
  status: OrderStatus
}

association places {
  Customer as customer [1]
  Order as orders [0..*]
}

composition contains {
  Order as order [1]
  OrderLine as lines [1..*]
}

association references {
  OrderLine as line [0..*]
  Product as product [1]
}
~~~

Trong ví dụ này, multiplicity ghi cạnh mỗi đầu cho biết số đối tượng ở đầu đó có thể liên kết với một đối tượng ở đầu đối diện:

- Mỗi Order có đúng một Customer; mỗi Customer có thể có `0..*` Order.
- Mỗi OrderLine thuộc đúng một Order; mỗi Order có từ một dòng hàng trở lên trong trạng thái được mô hình hóa.
- Mỗi OrderLine tham chiếu đúng một Product; một Product có thể xuất hiện trong nhiều OrderLine.

DSL có thể dùng các từ khóa `association`, `composition` hoặc cú pháp khác. Điều quan trọng là ngữ nghĩa phải được định nghĩa rõ: multiplicity ở đầu nào, vai trò nào, quan hệ có điều hướng hay không và composition có ràng buộc vòng đời nào.

### 6.1. Ràng buộc ngoài multiplicity

Multiplicity chỉ xác định số lượng liên kết. Nhiều quy tắc cần được mô tả bổ sung:

~~~text
constraint ConfirmedOrderHasLines {
  when Order.status == CONFIRMED
  require count(Order.lines) >= 1
}

constraint PositiveOrderLineQuantity {
  require OrderLine.quantity > 0
}

constraint ProductMustBeSellable {
  when Order.status == CONFIRMED
  require OrderLine.product.status == ACTIVE
}
~~~

Đây cũng là cú pháp giả định. Các ràng buộc minh họa rằng quy tắc có thể phụ thuộc vào trạng thái và dữ liệu liên quan. Chẳng hạn đơn hàng nháp có thể chưa có dòng hàng, nhưng đơn hàng đã xác nhận phải có ít nhất một dòng.

Một DSL có thể phân biệt ràng buộc cấu trúc (kiểm tra khi tạo hoặc phân tích mô hình) với quy tắc nghiệp vụ (kiểm tra khi một hành động xảy ra). Phân biệt này giúp bộ thực thi biết khi nào cần xác minh từng điều kiện.

### 6.2. Kiểm tra quan hệ trong bộ phân tích DSL

Khi DSL mô tả quan hệ, bộ phân tích hoặc bộ kiểm tra ngữ nghĩa có thể xác minh:

- Hai đầu quan hệ có tham chiếu đến khái niệm đã khai báo không?
- Vai trò có tên rõ ràng và không xung đột trong phạm vi không?
- Multiplicity có đúng cú pháp và giới hạn hợp lệ không?
- Loại quan hệ có tương thích với số đầu và ngữ nghĩa đã định nghĩa không?
- Một composition có vi phạm quy tắc sở hữu duy nhất không?
- Các ràng buộc có tham chiếu đến thuộc tính hoặc quan hệ tồn tại không?
- Có vòng phụ thuộc hoặc chu trình bị cấm theo quy tắc miền không?

Phân tích cú pháp thành công chỉ chứng minh văn bản đúng cấu trúc. Kiểm tra ngữ nghĩa mới xác định các khái niệm, quan hệ và ràng buộc có hợp lệ trong mô hình hay không.

## 7. Từ mô hình quan hệ đến mã và cơ sở dữ liệu

Mô hình miền thường được chuyển thành cấu trúc lớp, đối tượng, bảng và API. Tuy nhiên, không nên đồng nhất quan hệ nghiệp vụ với một chi tiết lưu trữ hoặc một trường tham chiếu trong mã.

### 7.1. Biểu diễn trong Java

Quan hệ một - nhiều giữa Customer và Order có thể được biểu diễn đơn giản:

~~~java
public class Customer {
    private CustomerId id;
    private String name;
}

public class Order {
    private OrderId id;
    private Customer customer;
    private List<OrderLine> lines;
}
~~~

Ở đây, Order giữ tham chiếu đến Customer và danh sách OrderLine. Đây là một cách biểu diễn trong mã; nó không tự đảm bảo các quy tắc như mỗi đơn hàng phải có khách hàng, đơn hàng đã xác nhận phải có dòng hàng hoặc dòng hàng không thể thuộc hai đơn hàng.

Những quy tắc đó cần được bảo vệ bằng constructor, phương thức nghiệp vụ, kiểm tra đầu vào, lớp miền hoặc các cơ chế phù hợp khác.

Ví dụ, thay vì cho phép sửa danh sách dòng hàng tùy ý từ bên ngoài, Order có thể cung cấp các phương thức `addLine`, `removeLine` và `confirm` để duy trì bất biến (invariant) của đơn hàng. Bất biến là điều kiện phải luôn đúng tại các trạng thái được mô hình cho phép.

### 7.2. Biểu diễn trong cơ sở dữ liệu quan hệ

Quan hệ Customer - Order một - nhiều thường được triển khai bằng khóa ngoại:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    CONSTRAINT fk_orders_customer
      FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Khóa ngoại đảm bảo mỗi giá trị customer_id tham chiếu đến một khách hàng tồn tại, còn NOT NULL yêu cầu trường phải có giá trị. Đây là các ràng buộc dữ liệu quan trọng.

Tuy nhiên, cấu trúc này chưa mô tả toàn bộ quy tắc miền. Nó không tự bảo đảm khách hàng được phép đặt đơn, đơn hàng đã xác nhận phải có dòng hàng hoặc đơn hàng không thể bị xóa theo chính sách lưu trữ. Những điều kiện đó có thể cần được thực thi ở tầng ứng dụng, cơ sở dữ liệu hoặc quy trình nghiệp vụ.

### 7.3. Quan hệ trong ORM

Các công cụ ORM như JPA có thể ánh xạ association giữa các lớp thành quan hệ khóa ngoại hoặc bảng liên kết. Ví dụ:

~~~java
@Entity
public class Order {
    @ManyToOne(optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;
}
~~~

`@ManyToOne` mô tả nhiều Order có thể tham chiếu một Customer. `optional = false` và `nullable = false` thể hiện yêu cầu bắt buộc ở các mức tương ứng của ánh xạ. Các chi tiết đồng bộ hai chiều, cascade, fetch và vòng đời cần được cấu hình có chủ đích.

Không nên bật cascade xóa hoặc dùng composition chỉ vì muốn ORM tự động xóa bản ghi liên quan. Cần dựa trên ý nghĩa nghiệp vụ và chính sách lưu trữ. Một sản phẩm được tham chiếu trong nhiều đơn hàng, chẳng hạn, không nên bị xóa chỉ vì một đơn hàng bị xóa.

## 8. Quan hệ thay đổi theo thời gian

Một mô hình tĩnh thường mô tả trạng thái hiện tại. Nhưng nhiều quan hệ nghiệp vụ có thời hạn hoặc thay đổi theo sự kiện.

Ví dụ, một Nhân viên có thể làm việc tại nhiều Phòng ban qua các giai đoạn khác nhau. Nếu chỉ lưu `employee.department`, hệ thống chỉ biết phòng ban hiện tại và mất lịch sử. Khi nghiệp vụ cần truy vấn lịch sử, có thể tạo khái niệm Phân công:

~~~text
entity Assignment {
  employee: Employee [1]
  department: Department [1]
  startDate: Date
  endDate: Date?
  role: JobRole
}
~~~

Mỗi Assignment liên kết một Nhân viên với một Phòng ban và lưu khoảng thời gian đảm nhiệm. Khi đó, cần thêm các quy tắc như ngày kết thúc không được trước ngày bắt đầu, hoặc một nhân viên không được có hai phân công toàn thời gian trùng lặp nếu chính sách không cho phép.

Một số quan hệ còn phụ thuộc trạng thái. Ví dụ, một Đơn hàng có thể tham chiếu đến Khách hàng trong suốt vòng đời, nhưng quyền chỉnh sửa của khách hàng thay đổi khi đơn hàng được xác nhận hoặc hoàn tất. Quan hệ cấu trúc vẫn tồn tại, còn hành vi được kiểm soát bởi trạng thái và quy tắc.

Khi mô hình hóa quan hệ theo thời gian, hãy xác định có cần lưu lịch sử, thời điểm bắt đầu/kết thúc, trạng thái hiệu lực và cách xử lý dữ liệu quá khứ hay không.

## 9. Quy trình xác định quan hệ giữa các khái niệm

Có thể thực hiện theo các bước sau khi phân tích một miền mới.

### Bước 1: Thu thập khái niệm

Từ yêu cầu nghiệp vụ, xác định các danh từ và cụm danh từ có ý nghĩa. Ví dụ với hệ thống thư viện: Độc giả, Thẻ thư viện, Sách, Bản sao sách, Phiếu mượn và Nhân viên.

Không phải mọi danh từ đều cần trở thành khái niệm độc lập. Một số chỉ là thuộc tính, nhãn hoặc thuật ngữ mô tả.

### Bước 2: Tìm động từ và câu mô tả nghiệp vụ

Đọc các tình huống sử dụng và tìm động từ kết nối các khái niệm:

- Độc giả mượn Bản sao sách.
- Phiếu mượn ghi nhận ngày mượn và hạn trả.
- Nhân viên lập Phiếu mượn.
- Bản sao sách thuộc về một đầu sách.

Những câu này là nguồn để nhận diện association và các khái niệm liên kết.

### Bước 3: Đặt tên vai trò và hai đầu quan hệ

Xác định mỗi bên tham gia với vai trò gì. Ví dụ, trong quan hệ Độc giả - Phiếu mượn, vai trò của Độc giả là “người mượn”, còn vai trò của Phiếu mượn là “các lượt mượn”.

### Bước 4: Xác định multiplicity

Hỏi các câu hỏi theo cả hai chiều:

- Một Phiếu mượn có đúng một Độc giả không?
- Một Độc giả có thể có nhiều Phiếu mượn đang hoạt động không?
- Một Phiếu mượn có thể chứa nhiều Bản sao sách không?
- Một Bản sao sách có thể đồng thời nằm trong nhiều Phiếu mượn đang hoạt động không?

Các câu trả lời cần dựa trên quy tắc thực tế, không dựa vào suy đoán từ tên lớp.

### Bước 5: Xác định loại quan hệ và vòng đời

Hỏi bộ phận có tồn tại độc lập với toàn thể hay không, có thể được chia sẻ không và điều gì xảy ra khi toàn thể bị xóa hoặc kết thúc. Điều này giúp phân biệt association, aggregation và composition.

Nếu quan hệ chỉ biểu thị một khái niệm là loại cụ thể của khái niệm khác, hãy xem xét generalization. Nếu một thành phần chỉ sử dụng dịch vụ khác để thực hiện thao tác, có thể đó là dependency.

### Bước 6: Xác định thuộc tính và ràng buộc của quan hệ

Nếu liên kết có dữ liệu riêng, hãy cân nhắc biến nó thành một khái niệm. Xác định thêm các điều kiện về trạng thái, thời gian, quyền, tính duy nhất và tính hợp lệ.

### Bước 7: Kiểm tra bằng tình huống thực tế

Dùng các kịch bản như tạo mới, cập nhật, hủy, chuyển giao, xóa, phục hồi và truy vấn lịch sử. Kiểm tra mô hình có diễn tả được tình huống hay không, và có trường hợp nào tạo ra trạng thái mâu thuẫn.

## 10. Ví dụ tổng hợp: mô hình miền thương mại điện tử

Một mô hình đơn giản có thể gồm Khách hàng, Đơn hàng, Dòng hàng, Sản phẩm và Thanh toán.

~~~text
Customer "1" <---- "0..*" Order
Order    "1" *---- "1..*" OrderLine
Product  "1" <---- "0..*" OrderLine
Order    "1" <---- "0..*" Payment
~~~

Đọc từng quan hệ:

- Một Customer có thể đặt nhiều Order; mỗi Order thuộc đúng một Customer.
- Một Order bao gồm một hoặc nhiều OrderLine trong trạng thái hợp lệ; mỗi OrderLine thuộc đúng một Order. Composition thể hiện Dòng hàng phụ thuộc vào Đơn hàng trong mô hình này.
- Một Product có thể được tham chiếu bởi nhiều OrderLine; mỗi OrderLine tham chiếu đúng một Product. Product tồn tại độc lập với đơn hàng.
- Một Order có thể có nhiều Payment, chẳng hạn thanh toán nhiều lần hoặc chia thành nhiều giao dịch; mỗi Payment gắn với một Order. Nếu nghiệp vụ chỉ cho phép một giao dịch, multiplicity cần thay đổi tương ứng.

Sơ đồ là mô hình khái niệm. Nó chưa mô tả mọi quy tắc, ví dụ:

- Tổng tiền đơn hàng phải phù hợp với các dòng hàng, thuế và giảm giá.
- Số lượng của mỗi dòng hàng phải lớn hơn không.
- Không thể xác nhận đơn hàng khi không có dòng hàng.
- Tổng số tiền thanh toán thành công không được vượt quá số tiền phải thu, trừ khi nghiệp vụ có cơ chế hoàn hoặc điều chỉnh.
- Đơn hàng đã hoàn tất có thể cần lưu ảnh chụp tên, mã và đơn giá sản phẩm tại thời điểm mua.

Các quy tắc này có thể được biểu diễn bằng constraint, phương thức nghiệp vụ hoặc chính sách của bộ thực thi DSL. Không nên cố gắng nhồi mọi quy tắc vào multiplicity hoặc một loại quan hệ duy nhất.

## 11. Những lỗi thường gặp khi mô hình hóa quan hệ

**Dùng tên quan hệ mơ hồ.** Tên như “có” hoặc “liên quan” không giải thích vai trò nghiệp vụ. Hãy dùng động từ cụ thể và đặt tên vai trò khi cần.

**Chỉ xác định số lượng ở một phía.** Một quan hệ phải được đọc từ cả hai đầu. Hãy kiểm tra multiplicity cho từng phía bằng câu hỏi nghiệp vụ tương ứng.

**Nhầm điều hướng với ý nghĩa quan hệ.** Một lớp có trường tham chiếu đến lớp khác không có nghĩa quan hệ chỉ tồn tại theo một chiều. Điều hướng là lựa chọn thiết kế truy cập; ý nghĩa nghiệp vụ cần được mô tả độc lập.

**Dùng composition cho mọi quan hệ một - nhiều.** Một khóa ngoại hoặc một danh sách đối tượng không tự chứng minh bộ phận phụ thuộc vòng đời vào toàn thể. Chỉ dùng composition khi có ý nghĩa sở hữu mạnh và quy tắc vòng đời phù hợp.

**Dùng kế thừa thay cho quan hệ vai trò.** Một Nhân viên không nhất thiết là một Quản lý theo nghĩa lớp con; quản lý có thể là vai trò mà nhân viên đảm nhiệm trong một khoảng thời gian. Nếu vai trò có thể thay đổi hoặc kết hợp, mô hình bằng quan hệ và khái niệm vai trò thường phù hợp hơn.

**Bỏ qua thuộc tính của liên kết.** Khi một quan hệ cần ngày bắt đầu, trạng thái, số lượng, thứ tự hoặc thông tin phê duyệt, hãy xem xét mô hình hóa liên kết thành khái niệm riêng.

**Đồng nhất mô hình miền với lược đồ cơ sở dữ liệu.** Mô hình miền diễn đạt ý nghĩa và quy tắc nghiệp vụ. Lược đồ dữ liệu là một cách lưu trữ. Một mô hình có thể được ánh xạ sang nhiều cách lưu trữ khác nhau mà vẫn giữ ngữ nghĩa.

**Bỏ qua lịch sử và trạng thái.** Quan hệ hiện tại có thể không đủ để trả lời câu hỏi về quá khứ. Nếu nghiệp vụ cần lịch sử, hãy mô hình hóa thời gian hiệu lực hoặc các sự kiện thay đổi.

## 12. Kết luận

Quan hệ kết nối các khái niệm thành một mô hình miền có ý nghĩa. Khi mô tả quan hệ, cần làm rõ tên, vai trò, multiplicity, hướng truy cập, loại quan hệ, thuộc tính liên kết và các ràng buộc nghiệp vụ. Association, aggregation, composition, generalization và dependency diễn đạt những ý nghĩa khác nhau; không nên sử dụng thay thế tùy tiện.

Trong DSL, các quan hệ cần được biểu diễn bằng cú pháp có ngữ nghĩa rõ ràng để bộ phân tích có thể kiểm tra cấu trúc và tính hợp lệ của mô hình. Khi chuyển sang mã hoặc cơ sở dữ liệu, cần bảo toàn ý nghĩa miền và thực thi các bất biến tương ứng.

Hãy bắt đầu từ câu chuyện nghiệp vụ: đối tượng nào liên quan đến đối tượng nào, vì sao liên quan, mỗi bên có vai trò gì và những điều kiện nào phải luôn đúng. Khi trả lời được các câu hỏi đó, mô hình quan hệ sẽ trở thành nền tảng đáng tin cậy cho thiết kế DSL và hệ thống sử dụng nó.

