# Vị trí của E2E trong danh mục kiểm chứng hành trình

Trong module `VALIDATION_TESTING_STRATEGY`, kiểm thử đầu cuối (End-to-End Testing, viết tắt là E2E) xác nhận một hành trình nghiệp vụ có thể hoàn tất qua những thành phần và ranh giới hệ thống quan trọng. E2E giúp trả lời câu hỏi: khi người dùng hoặc một tác nhân nghiệp vụ thực hiện công việc từ điểm bắt đầu đến kết quả cuối cùng, sản phẩm có phối hợp đúng các thành phần để tạo ra kết quả mong đợi hay không?

E2E có vai trò quan trọng vì một chức năng riêng lẻ có thể hoạt động đúng trong khi toàn bộ hành trình vẫn thất bại. Ví dụ, màn hình thanh toán hiển thị thành công, dịch vụ thanh toán trả về kết quả hợp lệ, nhưng đơn hàng không được xác nhận hoặc tồn kho không được cập nhật. Chỉ kiểm thử riêng từng thành phần sẽ khó chứng minh kết quả nghiệp vụ xuyên suốt.

Tuy vậy, E2E có chi phí thực hiện và bảo trì cao hơn nhiều kiểm thử ở phạm vi hẹp. Một danh mục kiểm chứng hành trình tốt cần đặt E2E đúng vị trí: dùng để xác nhận những luồng quan trọng qua các ranh giới hệ thống, kết hợp với kiểm thử đơn vị, thành phần, hợp đồng và tích hợp để bao phủ chi tiết các quy tắc và tình huống. Bài học này giải thích vai trò của E2E, cách lựa chọn hành trình, cách phân bổ kiểm thử trong danh mục và cách duy trì bộ E2E đáng tin cậy.

## 1. E2E xác nhận điều gì?

### 1.1. Định nghĩa kiểm thử đầu cuối

Kiểm thử E2E xác minh một luồng công việc hoàn chỉnh từ điểm khởi đầu đến kết quả có ý nghĩa đối với người dùng hoặc nghiệp vụ, đi qua những thành phần và tích hợp cần thiết của hệ thống.

Một hành trình có thể đi qua:

- Giao diện người dùng hoặc kênh tiếp nhận yêu cầu.
- API và dịch vụ nghiệp vụ.
- Cơ sở dữ liệu hoặc kho dữ liệu.
- Hàng đợi, sự kiện và tác vụ xử lý bất đồng bộ.
- Dịch vụ nội bộ và nhà cung cấp bên ngoài.
- Hệ thống thông báo, đối soát, báo cáo hoặc vận hành.
- Điểm cuối nơi người dùng nhận được kết quả.

Phạm vi E2E không nhất thiết bao gồm mọi hệ thống của tổ chức. Nó cần bao phủ các ranh giới quan trọng để chứng minh hành trình đã đạt mục tiêu. Ví dụ, nếu mục tiêu là xác nhận đơn hàng được tạo và thanh toán, hành trình có thể kết thúc khi đơn ở trạng thái đã xác nhận và giao dịch thanh toán có thể đối soát. Việc giao hàng vật lý có thể thuộc một hành trình E2E khác.

### 1.2. Phân biệt hành trình, kịch bản và trường hợp kiểm thử

Ba khái niệm thường được dùng gần nhau:

- **Hành trình (journey):** chuỗi công việc hoặc trải nghiệm mà một tác nhân thực hiện để đạt mục tiêu.
- **Kịch bản hành trình (journey scenario):** một biến thể cụ thể của hành trình với điều kiện và kết quả xác định.
- **Trường hợp kiểm thử (test case):** các bước, dữ liệu, tiền điều kiện và kết quả mong đợi dùng để xác minh một hoặc nhiều điều kiện.

Ví dụ với hành trình mua hàng:

- Hành trình: khách chọn sản phẩm, đặt hàng, thanh toán và nhận xác nhận.
- Kịch bản: khách đã đăng nhập, sản phẩm còn hàng, thanh toán thành công.
- Trường hợp kiểm thử: tạo dữ liệu khách và sản phẩm, thêm vào giỏ, xác nhận đơn, thanh toán bằng phương thức thử nghiệm, sau đó kiểm tra đơn và giao dịch.

Một hành trình có thể có nhiều kịch bản. Không nên tạo một bài E2E riêng cho mọi tổ hợp dữ liệu; hãy chọn những biến thể có ý nghĩa và có thể chứng minh một rủi ro cụ thể.

### 1.3. E2E khác với kiểm thử giao diện

E2E thường được thực hiện qua giao diện người dùng vì cách đó mô phỏng hành vi người dùng. Tuy nhiên, không phải mọi kiểm thử giao diện đều là E2E và không phải mọi E2E đều cần thao tác qua trình duyệt.

- Kiểm thử giao diện có thể chỉ xác nhận một thành phần hiển thị, trạng thái nút hoặc thông báo.
- E2E qua giao diện có thể thực hiện hành trình từ đăng nhập đến hoàn tất giao dịch, xác minh kết quả tại nhiều điểm.
- E2E qua API có thể điều phối các API của nhiều dịch vụ để xác nhận một luồng nghiệp vụ mà không mô phỏng từng thao tác trên giao diện.
- E2E hỗn hợp có thể bắt đầu qua giao diện, kiểm tra kết quả bằng API hoặc dữ liệu kiểm soát, và xác nhận sự kiện bất đồng bộ.

Phương thức kiểm thử cần phù hợp với mục tiêu. Nếu cần xác nhận người dùng có thể hoàn tất hành trình bằng giao diện thực, cần có kiểm thử qua giao diện. Nếu cần kiểm tra quy trình xuyên dịch vụ với nhiều dữ liệu và nhánh lỗi, kiểm thử API hoặc tích hợp có thể hiệu quả hơn.

### 1.4. Kết quả E2E phải gắn với nghiệp vụ

Một kịch bản E2E không nên chỉ kết luận “không có lỗi trên màn hình”. Cần xác định kết quả nghiệp vụ cuối cùng, chẳng hạn:

- Đơn hàng được tạo đúng một lần.
- Số tiền được ghi nhận khớp với đơn.
- Tồn kho được giữ hoặc trừ theo chính sách.
- Người dùng nhận được thông báo đúng.
- Trạng thái giữa các hệ thống có thể đối soát.
- Không xuất hiện tác dụng phụ không mong muốn.

Kết quả cần có nguồn bằng chứng phù hợp. Giao diện có thể cho biết người dùng đã nhận xác nhận, còn bản ghi đơn và giao dịch chứng minh trạng thái được lưu ở hệ thống tương ứng.

## 2. Vị trí của E2E trong danh mục kiểm chứng

Danh mục kiểm chứng hành trình là tập hợp các kiểm thử được tổ chức theo hành trình nghiệp vụ, rủi ro, phạm vi và tầng kiểm thử. E2E là một phần của danh mục, thường nằm ở phạm vi rộng nhất trong số các kiểm thử tự động thường xuyên, nhưng cần được hỗ trợ bởi các tầng kiểm thử nhỏ hơn.

### 2.1. Các tầng kiểm thử bổ trợ cho nhau

| Tầng kiểm thử | Phạm vi chính | Câu hỏi được trả lời | Đặc điểm |
|---|---|---|---|
| Đơn vị (unit) | Hàm, lớp hoặc quy tắc nhỏ | Logic này có đúng với đầu vào đã cho không? | Nhanh, cô lập, dễ kiểm tra nhiều trường hợp |
| Thành phần (component) | Một thành phần hoặc dịch vụ với phụ thuộc được kiểm soát | Thành phần xử lý hợp đồng và trạng thái đúng không? | Kiểm tra sâu một đơn vị triển khai |
| Hợp đồng (contract) | Giao tiếp giữa bên cung cấp và bên tiêu thụ | Hai bên có thống nhất cấu trúc và ý nghĩa trao đổi không? | Phát hiện sai lệch giao diện sớm |
| Tích hợp (integration) | Tương tác giữa một số thành phần hoặc dịch vụ | Các thành phần phối hợp đúng tại ranh giới không? | Tập trung vào dữ liệu, giao thức và tương tác |
| Hệ thống (system) | Hành vi của hệ thống trong phạm vi đã xác định | Hệ thống có đáp ứng yêu cầu chức năng và phi chức năng không? | Có thể bao gồm nhiều luồng và điều kiện vận hành |
| Đầu cuối (E2E) | Hành trình xuyên qua các thành phần cần thiết | Người dùng hoặc nghiệp vụ có đạt kết quả cuối cùng không? | Phạm vi rộng, chi phí và độ phụ thuộc môi trường cao hơn |

Các tầng này không phải lúc nào cũng được phân biệt tuyệt đối. Một kiểm thử có thể đồng thời mang đặc điểm tích hợp và E2E tùy ranh giới được bao phủ. Điều quan trọng là mô tả rõ phạm vi thực tế, những phụ thuộc thật được sử dụng và điều gì được mô phỏng.

### 2.2. Mô hình phân bổ theo chiều rộng và chiều sâu

Một danh mục hiệu quả thường có nhiều kiểm thử nhanh ở tầng dưới, ít kiểm thử hơn ở tầng tích hợp và một tập E2E nhỏ tập trung vào hành trình trọng yếu.

```text
             E2E
       Hành trình cốt lõi
      -------------------
         Tích hợp
      Ranh giới quan trọng
    -------------------------
       Thành phần / Hợp đồng
    -----------------------------
              Đơn vị
       Quy tắc và nhánh chi tiết
```

Hình dạng này thường được gọi là kim tự tháp kiểm thử. Đây là định hướng phân bổ, không phải quy định rằng mọi dự án phải có một tỷ lệ cố định. Hệ thống có nhiều giao diện, dịch vụ và rủi ro liên kết có thể cần nhiều kiểm thử tích hợp hoặc E2E hơn. Hệ thống nhúng, sản phẩm phần cứng hoặc hệ thống có môi trường mô phỏng đặc thù có thể cần cách phân bổ khác.

Nguyên tắc quan trọng là kiểm tra chi tiết các quy tắc ở tầng có chi phí thấp và khả năng cô lập tốt; dùng E2E để xác nhận các kết quả xuyên suốt mà tầng dưới không thể chứng minh đầy đủ.

### 2.3. Vì sao không nên đẩy mọi trường hợp lên E2E?

Nếu kiểm tra mọi tổ hợp dữ liệu qua giao diện và toàn bộ hệ thống, bộ kiểm thử sẽ:

- Chạy lâu và làm chậm phản hồi cho nhóm phát triển.
- Phụ thuộc nhiều vào môi trường, mạng, dịch vụ bên ngoài và dữ liệu dùng chung.
- Dễ thất bại do timing, trạng thái bất đồng bộ hoặc thay đổi giao diện nhỏ.
- Khó xác định nguyên nhân khi một hành trình thất bại.
- Tốn công chuẩn bị và dọn dữ liệu.
- Khó mở rộng số lượng trường hợp khi yêu cầu thay đổi.

Ví dụ, quy tắc tính thuế có thể có hàng chục tổ hợp về khu vực, loại hàng và mức miễn giảm. Nên kiểm tra phần lớn tổ hợp ở tầng đơn vị hoặc thành phần với dữ liệu có kiểm soát. E2E chỉ cần một số hành trình đại diện để xác nhận tổng tiền được chuyển đúng từ giỏ hàng sang đơn, thanh toán và hóa đơn.

### 2.4. E2E không thay thế kiểm thử hồi quy ở tầng dưới

Một hành trình E2E thành công không chứng minh mọi quy tắc bên trong đều đúng. Nó chỉ chứng minh những điều kiện được đi qua và quan sát trong kịch bản đó. Một số lỗi hiếm, dữ liệu biên hoặc nhánh ngoại lệ có thể không xuất hiện trong hành trình đại diện.

Do đó, khi một lỗi được sửa ở tầng đơn vị, vẫn cần kiểm thử đơn vị tương ứng. Khi thay đổi hợp đồng giữa hai dịch vụ, cần kiểm thử hợp đồng và tích hợp. E2E bổ sung sự bảo đảm ở cấp hành trình, không thay thế các bằng chứng chuyên biệt.

## 3. Khi nào nên dùng E2E?

E2E phù hợp khi mục tiêu kiểm chứng phụ thuộc vào sự phối hợp của nhiều thành phần hoặc khi hậu quả nghiệp vụ chỉ có thể đánh giá ở kết quả cuối cùng.

### 3.1. Những trường hợp có giá trị cao

Ưu tiên E2E cho:

- Hành trình tạo ra giá trị cốt lõi của sản phẩm, như đăng ký, đặt hàng, thanh toán, đặt lịch hoặc xử lý yêu cầu.
- Luồng đi qua nhiều dịch vụ hoặc ranh giới tổ chức.
- Quy trình có trạng thái và dữ liệu cần nhất quán qua nhiều bước.
- Các tích hợp có lịch sử lỗi hoặc có thể gây hậu quả lớn.
- Hành trình có nhiều vai trò hoặc điểm chuyển giao giữa người dùng và nhân viên.
- Quy trình quan trọng cần xác nhận trước khi phát hành.
- Các đường đi phổ biến mà người dùng thực sự thực hiện.

### 3.2. Những trường hợp nên kiểm tra ở tầng khác

Ưu tiên tầng nhỏ hơn khi:

- Cần kiểm tra nhiều giá trị biên hoặc tổ hợp dữ liệu.
- Cần xác minh quy tắc tính toán thuần túy.
- Cần thử hàng loạt lỗi đầu vào hoặc điều kiện hiếm.
- Cần xác nhận chi tiết một giao diện dịch vụ.
- Cần mô phỏng lỗi của một phụ thuộc mà E2E thật khó tạo ra.
- Cần kiểm tra một nhánh kỹ thuật không đại diện cho hành trình người dùng.
- Hành vi chưa ổn định hoặc chưa có môi trường E2E đáng tin cậy.

Có thể dùng kiểm thử thành phần hoặc tích hợp với mô phỏng để bao phủ các nhánh khó tái tạo ở E2E, sau đó giữ một số E2E cho kết quả chính của hành trình.

### 3.3. Đánh giá giá trị so với chi phí

Trước khi đưa một trường hợp vào bộ E2E, hãy hỏi:

1. Hành trình này có quan trọng với mục tiêu sản phẩm hoặc người dùng không?
2. Có rủi ro nào chỉ có thể phát hiện đáng tin cậy khi đi qua nhiều thành phần không?
3. Kiểm thử ở tầng dưới đã bao phủ chi tiết các quy tắc chưa?
4. E2E sẽ cung cấp bằng chứng bổ sung nào?
5. Có thể tạo và dọn dữ liệu ổn định không?
6. Các phụ thuộc có thể được kiểm soát hoặc quan sát không?
7. Chi phí chạy và bảo trì có tương xứng với hậu quả nếu lỗi xảy ra không?

Nếu một trường hợp chỉ lặp lại logic đã được kiểm tra sâu ở tầng đơn vị mà không xác nhận thêm hành vi xuyên hệ thống, giá trị tăng thêm của E2E có thể thấp.

## 4. Xây dựng danh mục hành trình E2E

Một danh mục tốt bắt đầu từ mục tiêu và hành trình của người dùng, sau đó chọn những đường đi đại diện theo rủi ro.

### 4.1. Liệt kê hành trình theo tác nhân và mục tiêu

Xác định các tác nhân chính và công việc họ cần hoàn thành. Ví dụ với một nền tảng thương mại điện tử:

| Tác nhân | Mục tiêu | Hành trình có thể cần kiểm chứng |
|---|---|---|
| Khách chưa đăng nhập | Tìm và mua sản phẩm | Tìm kiếm, xem sản phẩm, mua với tư cách khách |
| Khách đã đăng nhập | Quản lý đơn và thông tin cá nhân | Đăng nhập, đặt hàng, xem lịch sử, hủy đơn theo chính sách |
| Nhân viên vận hành | Xử lý đơn và ngoại lệ | Xem đơn, xác nhận, xử lý trường hợp thanh toán bất thường |
| Bộ phận tài chính | Đối soát giao dịch | Kiểm tra giao dịch, hoàn tiền, đối chiếu báo cáo |
| Quản trị viên | Quản lý quyền và cấu hình | Cập nhật cấu hình, quản lý vai trò và kiểm tra quyền |

Không phải mọi mục tiêu đều cần E2E riêng. Chọn hành trình có tác động cao, tần suất đáng kể hoặc nhiều ranh giới phối hợp.

### 4.2. Xác định điểm bắt đầu, điểm kết thúc và ranh giới

Mỗi hành trình cần mô tả:

- Tác nhân và trạng thái ban đầu.
- Sự kiện khởi đầu.
- Các bước nghiệp vụ chính.
- Thành phần và hệ thống cần đi qua.
- Điểm ra quyết định và nhánh ngoại lệ.
- Kết quả cuối cùng và bằng chứng xác nhận.
- Những hệ thống hoặc bước được mô phỏng hay nằm ngoài phạm vi.

Ví dụ, hành trình “mua hàng thành công” có thể bắt đầu khi khách có giỏ hàng hợp lệ và kết thúc khi đơn được xác nhận, thanh toán được ghi nhận và khách nhận thông báo. Nếu dịch vụ giao hàng không thuộc mục tiêu, không cần giả định rằng E2E này phải xác nhận kiện hàng đã giao.

### 4.3. Chọn kịch bản đại diện

Với mỗi hành trình, chọn một số kịch bản dựa trên rủi ro:

- Luồng chính thành công.
- Một hoặc hai nhánh thay thế có tần suất hoặc hậu quả đáng kể.
- Một tình huống lỗi xuyên hệ thống cần kiểm soát.
- Một tình huống phục hồi nếu trạng thái có thể bị lệch.

Ví dụ:

| Hành trình | Kịch bản E2E đại diện | Bằng chứng cuối |
|---|---|---|
| Đặt hàng | Sản phẩm còn hàng, thanh toán thành công | Đơn xác nhận, giao dịch khớp, thông báo được gửi |
| Đặt hàng | Thanh toán bị từ chối | Đơn không ở trạng thái đã thanh toán; người dùng nhận thông báo phù hợp |
| Hủy đơn | Hủy đơn trong trạng thái được phép | Đơn hủy, tồn kho và hoàn tiền theo chính sách |
| Đăng ký | Người dùng đăng ký với thông tin hợp lệ | Tài khoản được tạo và trạng thái xác minh đúng |
| Đặt lịch | Đặt khung giờ còn chỗ | Lịch được tạo, số chỗ cập nhật và xác nhận được gửi |

Không cần kiểm tra mọi trường hợp mã lỗi của cổng thanh toán qua E2E. Các mã và điều kiện chi tiết có thể được kiểm tra ở tầng tích hợp hoặc hợp đồng; E2E giữ các kịch bản đại diện chứng minh kết quả nghiệp vụ.

### 4.4. Ưu tiên theo rủi ro và độ quan trọng của hành trình

Có thể đánh giá hành trình theo:

- Giá trị với người dùng và hoạt động kinh doanh.
- Số lượng người dùng hoặc giao dịch bị ảnh hưởng.
- Mức độ nghiêm trọng nếu hành trình thất bại.
- Số lượng thành phần và hệ thống tham gia.
- Tần suất sử dụng.
- Lịch sử sự cố và độ ổn định hiện tại.
- Khả năng phát hiện vấn đề qua giám sát vận hành.

Một ma trận đơn giản:

| Mức ưu tiên | Đặc điểm | Phân bổ E2E |
|---|---|---|
| Rất cao | Luồng cốt lõi, hậu quả nghiêm trọng hoặc nhiều phụ thuộc quan trọng | Có E2E cho luồng chính và nhánh rủi ro trọng yếu; chạy ở các mốc phát hành phù hợp |
| Cao | Luồng thường dùng, ảnh hưởng đáng kể đến người dùng | Có E2E đại diện; chạy theo lịch hồi quy hoặc trước phát hành |
| Trung bình | Luồng ít dùng hơn, tác động có thể kiểm soát | Cân nhắc E2E khi có rủi ro xuyên hệ thống; phần chi tiết ở tầng dưới |
| Thấp | Hành vi ít ảnh hưởng, dễ phát hiện và phục hồi | Ưu tiên kiểm thử ở tầng nhỏ hơn; E2E chỉ khi có giá trị bổ sung |

Mức ưu tiên không cố định. Một hành trình ít dùng vẫn có thể cần E2E nếu liên quan đến quyền riêng tư, tiền, an toàn hoặc nghĩa vụ quan trọng.

## 5. Ví dụ: phân bổ kiểm chứng cho hành trình mua hàng

Giả sử hành trình mua hàng đi qua giao diện cửa hàng, dịch vụ giỏ hàng, dịch vụ đơn hàng, tồn kho, cổng thanh toán và hệ thống thông báo.

### 5.1. Mục tiêu nghiệp vụ

Khách có thể mua sản phẩm còn hàng, thanh toán đúng số tiền và nhận xác nhận đơn. Hệ thống không tạo đơn hoặc giao dịch trùng khi người dùng gửi lại yêu cầu.

### 5.2. Phân bổ kiểm thử theo tầng

| Nội dung cần xác minh | Tầng phù hợp | Lý do |
|---|---|---|
| Công thức tính tổng giá, giảm giá và thuế với nhiều tổ hợp | Đơn vị | Có thể kiểm tra nhiều dữ liệu nhanh và cô lập |
| Quy tắc giữ tồn kho và từ chối khi hết hàng | Thành phần / tích hợp | Cần xác nhận xử lý dữ liệu và tương tác với kho |
| Cấu trúc và ý nghĩa yêu cầu gửi sang cổng thanh toán | Hợp đồng | Xác nhận hai bên thống nhất giao tiếp |
| Xử lý timeout, thông báo lặp và thử lại | Tích hợp | Cần kiểm tra hành vi tại ranh giới dịch vụ |
| Khách hoàn tất mua hàng qua giao diện và nhận xác nhận | E2E | Chứng minh hành trình cốt lõi qua các thành phần |
| Trạng thái đơn, giao dịch và thông báo nhất quán | E2E kết hợp đối soát | Xác nhận kết quả cuối ở nhiều điểm có thẩm quyền |

### 5.3. Một kịch bản E2E thành công

```gherkin
Feature: Mua hàng

  Scenario: Khách mua sản phẩm còn hàng và thanh toán thành công
    Given khách có một giỏ hàng hợp lệ
      And sản phẩm còn đủ tồn kho
      And cổng thanh toán thử nghiệm sẵn sàng
    When khách xác nhận đặt hàng
      And hoàn tất thanh toán
    Then hệ thống tạo một đơn hàng đã xác nhận
      And giao dịch thanh toán khớp với tổng tiền đơn hàng
      And tồn kho được cập nhật theo chính sách
      And khách nhận được thông báo xác nhận
```

Kịch bản cần có dữ liệu kiểm thử riêng và cơ chế dọn dữ liệu sau khi chạy. Khi kiểm tra giao dịch, dùng mã tương quan hoặc mã đơn để xác định đúng bản ghi thay vì chỉ tìm một giao dịch bất kỳ.

### 5.4. Kịch bản lỗi và phạm vi phù hợp

Nếu cổng thanh toán từ chối, E2E có thể xác nhận khách nhìn thấy kết quả phù hợp và đơn không bị ghi nhận đã thanh toán. Các mã từ chối, trường hợp chữ ký sai hoặc cấu trúc phản hồi lỗi nên được kiểm tra sâu hơn ở tầng hợp đồng và tích hợp.

Nếu phản hồi bị timeout sau khi cổng thanh toán đã xử lý giao dịch, đây là rủi ro xuyên hệ thống đáng cân nhắc cho một E2E đại diện. Kịch bản cần xác minh hệ thống không thu tiền lần hai khi thử lại và có thể đối soát trạng thái. Việc tạo tình huống này cần môi trường thử nghiệm hoặc mô phỏng được kiểm soát.

## 6. Thiết kế E2E đáng tin cậy

E2E đi qua nhiều thành phần nên dễ bị ảnh hưởng bởi dữ liệu, môi trường và thời gian xử lý. Thiết kế tốt giúp kết quả phản ánh lỗi sản phẩm thay vì nhiễu từ hạ tầng kiểm thử.

### 6.1. Quản lý dữ liệu kiểm thử

Dữ liệu E2E cần:

- Có thể tạo và nhận diện riêng cho mỗi lần chạy.
- Đại diện cho điều kiện nghiệp vụ cần kiểm chứng.
- Không chứa dữ liệu cá nhân hoặc bí mật thật nếu chưa được cho phép.
- Không xung đột giữa các lần chạy song song.
- Có thể dọn hoặc đưa về trạng thái ban đầu an toàn.
- Có mã tương quan để truy vết qua nhiều hệ thống.

Tránh dùng một tài khoản hoặc một đơn hàng cố định cho nhiều kiểm thử đồng thời. Hai kịch bản có thể thay đổi cùng một trạng thái và gây lỗi không ổn định. Có thể tạo dữ liệu theo mã chạy duy nhất hoặc cấp bộ dữ liệu độc lập.

### 6.2. Kiểm soát môi trường và phụ thuộc

Ghi rõ:

- Phiên bản ứng dụng và cấu hình đang kiểm thử.
- Dịch vụ thật, dịch vụ giả lập và điểm nào được thay thế.
- Tài khoản, quyền truy cập và dữ liệu được cấp.
- Trạng thái của hàng đợi, tác vụ nền và dịch vụ bên ngoài.
- Điều kiện mạng, thời gian chờ và giới hạn tài nguyên.
- Cách khởi tạo và dọn môi trường.

Nếu một dịch vụ quan trọng được thay bằng mock, kiểm thử không còn xác nhận tích hợp thật qua ranh giới đó. Điều này có thể phù hợp để kiểm tra một hành trình với phụ thuộc được kiểm soát, nhưng phải ghi rõ giới hạn bằng chứng và có kiểm thử tích hợp riêng cho dịch vụ thật.

### 6.3. Xử lý bất đồng bộ

Một số bước không hoàn tất ngay sau thao tác của người dùng, chẳng hạn gửi email, xử lý thanh toán hoặc cập nhật báo cáo. Không nên dùng thời gian chờ cố định quá dài hoặc giả định mọi bước hoàn tất tức thì.

Nên:

- Chờ theo điều kiện có thể quan sát, với thời hạn tối đa rõ ràng.
- Dùng mã tương quan để theo dõi sự kiện và bản ghi liên quan.
- Phân biệt trạng thái trung gian hợp lệ với trạng thái cuối.
- Xác định thời hạn hoàn tất theo yêu cầu nghiệp vụ.
- Thu thập log hoặc dấu vết khi quá thời hạn.
- Tránh lặp thao tác gây tác dụng phụ chỉ vì chưa nhận được phản hồi.

### 6.4. Chọn điểm xác minh ổn định

Khi kiểm thử giao diện, dùng định danh phần tử ổn định như thuộc tính truy cập hoặc test ID đã thống nhất. Tránh phụ thuộc vào vị trí, màu sắc hoặc cấu trúc DOM dễ thay đổi nếu những chi tiết đó không phải mục tiêu kiểm thử.

Kết quả nên được kiểm tra ở nhiều điểm có ý nghĩa:

- Giao diện hiển thị điều người dùng cần biết.
- API hoặc dịch vụ trả về trạng thái đúng.
- Dữ liệu nghiệp vụ được lưu đúng.
- Sự kiện hoặc thông báo được phát ra theo yêu cầu.
- Không có bản ghi trùng hoặc tác dụng phụ sai.

Không cần kiểm tra mọi tầng trong mọi kịch bản. Chọn điểm xác minh đủ để chứng minh mục tiêu và giúp chẩn đoán khi thất bại.

### 6.5. Giữ kịch bản độc lập và có thể lặp lại

Mỗi E2E nên tự chuẩn bị dữ liệu, thực hiện hành trình và dọn trạng thái trong phạm vi được phép. Kịch bản không nên phụ thuộc vào việc một E2E khác chạy trước và để lại dữ liệu.

Nếu cần kiểm tra chuỗi nhiều hành trình có quan hệ, hãy coi đó là một kịch bản tổng hợp có chủ đích và ghi rõ thứ tự. Nếu không, chia thành các kịch bản độc lập để có thể chạy riêng hoặc song song.

### 6.6. Tránh flaky test

Flaky test là kiểm thử có cùng mã và điều kiện nhưng lúc đạt lúc không do yếu tố không ổn định như timing, dữ liệu chia sẻ, mạng hoặc môi trường.

Cách giảm:

- Chờ điều kiện thay vì ngủ một khoảng thời gian tùy ý.
- Cô lập dữ liệu và tài khoản giữa các lần chạy.
- Dùng môi trường và phụ thuộc có trạng thái xác định.
- Tránh phụ thuộc vào thứ tự chạy.
- Xác định rõ thời hạn cho xử lý bất đồng bộ.
- Ghi lại log, ảnh chụp và mã tương quan khi thất bại.
- Phân loại lỗi sản phẩm, lỗi môi trường và lỗi kiểm thử.
- Không tự động retry vô hạn để che giấu lỗi không ổn định.

Khi một E2E flaky, cần tìm nguyên nhân và sửa. Retry có kiểm soát có thể hỗ trợ chẩn đoán trong thời gian ngắn, nhưng không nên biến một kiểm thử không đáng tin thành tín hiệu đạt.

## 7. Tổ chức chạy E2E trong vòng đời phát triển

Không phải tất cả E2E cần chạy ở mọi lần commit. Hãy phân bổ theo tốc độ phản hồi và mức độ rủi ro.

### 7.1. Các mốc chạy phù hợp

| Mốc | Phạm vi gợi ý | Mục tiêu |
|---|---|---|
| Khi phát triển tính năng | E2E mục tiêu trên hành trình liên quan nếu môi trường đủ ổn định | Phản hồi sớm về luồng bị thay đổi |
| Pull request / tích hợp liên tục | Smoke và một tập E2E cốt lõi nhanh | Phát hiện lỗi nghiêm trọng trước khi hợp nhất |
| Build định kỳ | Bộ E2E rộng hơn với nhiều hành trình và biến thể | Phát hiện lỗi lan rộng |
| Trước phát hành | E2E rủi ro cao trên môi trường gần sản xuất | Xác nhận hành trình trọng yếu trong cấu hình phát hành |
| Sau triển khai | Smoke hoặc synthetic journey được kiểm soát | Xác nhận dịch vụ thực tế hoạt động sau phát hành |

Một số tổ chức chạy E2E trên mỗi pull request khi bộ kiểm thử nhỏ và ổn định. Tổ chức khác chạy tập cốt lõi trên pull request và tập rộng theo lịch. Quyết định phụ thuộc vào thời gian phản hồi, năng lực môi trường, mức rủi ro và chi phí bảo trì.

### 7.2. Tách smoke test, hồi quy và giám sát hành trình

Các hoạt động này có liên quan nhưng mục tiêu khác nhau:

- **Smoke test:** kiểm tra nhanh các chức năng cơ bản để xác định bản dựng hoặc môi trường có đủ điều kiện cho kiểm thử sâu hơn.
- **E2E hồi quy:** chạy lại các hành trình đã chọn để phát hiện tác động ngoài dự kiến từ thay đổi.
- **Synthetic monitoring:** định kỳ mô phỏng một số thao tác hoặc yêu cầu trên môi trường đang vận hành để phát hiện suy giảm dịch vụ.

Một synthetic journey có thể giống E2E về thao tác, nhưng phục vụ giám sát vận hành, cần quản lý tần suất, dữ liệu và tác dụng phụ cẩn thận. Một bộ E2E trong môi trường kiểm thử không thay thế giám sát trên hệ thống thật.

### 7.3. Đánh giá kết quả chạy

Báo cáo E2E cần phân biệt:

- Đạt: hành trình hoàn tất và các kết quả mong đợi được xác minh.
- Không đạt: hành vi thực tế khác tiêu chí hoặc có tác dụng phụ sai.
- Bị chặn: không thể thực hiện do môi trường, dữ liệu, quyền hoặc phụ thuộc.
- Không ổn định: kết quả thay đổi giữa các lần chạy trong điều kiện tương đương.
- Bỏ qua: không chạy theo quyết định phạm vi đã ghi nhận.

Khi thất bại, cần có đủ bằng chứng để xác định bước nào lỗi, dữ liệu nào liên quan và các hệ thống nào đã nhận tác động. Không nên đánh dấu đạt nếu chỉ có thao tác đầu vào thành công nhưng chưa xác nhận kết quả cuối.

## 8. Quản lý và cải tiến danh mục E2E

Danh mục E2E cần được xem như một tài sản sống. Hành trình, sản phẩm, rủi ro và kiến trúc thay đổi; bộ kiểm thử cũng cần được cập nhật.

### 8.1. Thông tin cần quản lý cho mỗi hành trình

| Trường | Nội dung |
|---|---|
| Journey ID | Mã định danh hành trình |
| Tên hành trình | Mục tiêu nghiệp vụ ngắn gọn |
| Tác nhân | Người dùng, vai trò hoặc hệ thống khởi tạo |
| Điểm bắt đầu và kết thúc | Điều kiện đầu và kết quả cuối |
| Mức ưu tiên | Dựa trên giá trị, tần suất và rủi ro |
| Phụ thuộc | Thành phần, dịch vụ và hệ thống ngoài |
| Kịch bản E2E | Các biến thể được kiểm tra |
| Tầng bổ trợ | Unit, component, contract hoặc integration liên quan |
| Môi trường | Môi trường và cấu hình sử dụng |
| Dữ liệu | Cách tạo, nhận diện và dọn dữ liệu |
| Bằng chứng | Nguồn xác minh kết quả |
| Tần suất chạy | Pull request, định kỳ, trước phát hành hoặc sau triển khai |
| Chủ sở hữu | Người chịu trách nhiệm duy trì |
| Giới hạn | Thành phần mô phỏng, rủi ro chưa bao phủ và điều kiện đặc biệt |

### 8.2. Đánh giá hiệu quả bộ E2E

Theo dõi các chỉ số có ý nghĩa:

- Tỷ lệ hành trình quan trọng được bao phủ.
- Tỷ lệ chạy đạt, không đạt, bị chặn và không ổn định.
- Thời gian chạy của tập E2E cốt lõi và tập rộng.
- Thời gian trung bình để xác định nguyên nhân lỗi.
- Số lỗi thực tế được phát hiện trước phát hành.
- Số lỗi hồi quy lọt qua bộ kiểm thử.
- Chi phí bảo trì và số kịch bản lỗi thời.
- Mức độ trùng lặp giữa E2E và kiểm thử tầng dưới.

Không nên tối ưu chỉ số tỷ lệ đạt bằng cách xóa các kịch bản khó hoặc nới lỏng tiêu chí. Hãy xem xét giá trị phát hiện lỗi, độ tin cậy và khả năng cung cấp bằng chứng của từng kịch bản.

### 8.3. Khi nào cần thêm, sửa hoặc loại bỏ E2E?

**Thêm E2E** khi xuất hiện hành trình cốt lõi mới, một tích hợp quan trọng mới hoặc sự cố cho thấy cần xác nhận kết quả xuyên hệ thống.

**Sửa E2E** khi quy trình, giao diện, dữ liệu, trạng thái hoặc hợp đồng thay đổi. Cập nhật tiền điều kiện, kết quả mong đợi và nguồn bằng chứng.

**Loại bỏ E2E** khi hành trình không còn được hỗ trợ, kịch bản trùng lặp mà không cung cấp thêm bảo đảm, hoặc chi phí bảo trì vượt giá trị. Trước khi loại, xác nhận rủi ro được bao phủ ở đâu và cập nhật ma trận truy vết.

### 8.4. Duy trì tính đại diện

Một bộ E2E nhỏ không có nghĩa là chỉ kiểm tra một người dùng hoặc một cấu hình. Dữ liệu và biến thể cần đại diện cho các điều kiện quan trọng như vai trò, loại khách hàng, khu vực, phương thức thanh toán hoặc thiết bị được hỗ trợ.

Hãy dùng phân tích rủi ro để chọn tổ hợp đại diện, còn các tổ hợp chi tiết có thể được bao phủ ở tầng thấp hơn. Khi có sự cố thực tế, xem xét liệu danh mục có thiếu hành trình hoặc điều kiện quan trọng hay không.

## 9. Những sai lầm thường gặp

1. **Đưa mọi trường hợp lên E2E:** làm bộ kiểm thử chậm, khó bảo trì và khó chẩn đoán.
2. **Chỉ kiểm tra giao diện:** không xác minh kết quả nghiệp vụ và dữ liệu cuối cùng.
3. **Không xác định ranh giới thật:** gọi một kịch bản là E2E dù các dịch vụ quan trọng đều bị mock.
4. **Chỉ có luồng thành công:** bỏ qua từ chối, hủy, thử lại và phục hồi ở các hành trình rủi ro cao.
5. **Dùng dữ liệu dùng chung:** khiến các lần chạy tranh chấp trạng thái và tạo kết quả không ổn định.
6. **Chờ theo thời gian cố định:** làm kiểm thử chậm hoặc thất bại ngẫu nhiên khi hệ thống xử lý bất đồng bộ.
7. **Không có bằng chứng ở điểm cuối:** chỉ xác nhận nút đã được nhấn hoặc trang đã chuyển.
8. **Coi retry là giải pháp:** che giấu nguyên nhân flaky thay vì sửa dữ liệu, timing hoặc môi trường.
9. **Chạy E2E quá muộn:** phát hiện lỗi tích hợp sau khi nhiều thay đổi đã tích lũy.
10. **Không duy trì danh mục:** để kịch bản lỗi thời, trùng lặp hoặc không còn đại diện cho hành trình hiện tại.

## 10. Checklist khi phân bổ E2E trong danh mục kiểm chứng hành trình

- [ ] Đã xác định các hành trình và mục tiêu nghiệp vụ quan trọng.
- [ ] Mỗi hành trình có tác nhân, điểm bắt đầu, điểm kết thúc và kết quả mong đợi rõ ràng.
- [ ] Đã xác định các thành phần và ranh giới hệ thống thực sự cần được xác nhận.
- [ ] Đã chọn kịch bản E2E theo giá trị, tần suất và rủi ro.
- [ ] Các quy tắc và tổ hợp dữ liệu chi tiết được phân bổ về tầng phù hợp.
- [ ] Đã phân biệt E2E với kiểm thử giao diện, smoke test và synthetic monitoring.
- [ ] Đã ghi rõ dịch vụ thật, dịch vụ mô phỏng và giới hạn bằng chứng.
- [ ] Dữ liệu, tài khoản và môi trường có thể tạo, cô lập và dọn an toàn.
- [ ] Các bước bất đồng bộ có điều kiện chờ và thời hạn xác định.
- [ ] Kết quả cuối được xác minh bằng nguồn dữ liệu hoặc bằng chứng có thẩm quyền.
- [ ] Bộ E2E có lịch chạy phù hợp với vòng đời phát triển và phát hành.
- [ ] Có cơ chế phân loại lỗi sản phẩm, lỗi môi trường và lỗi kiểm thử.
- [ ] Có người chịu trách nhiệm duy trì và xem xét danh mục định kỳ.
- [ ] Rủi ro chưa được E2E bao phủ được ghi nhận và có tầng kiểm thử bổ trợ.

E2E có giá trị cao nhất khi chứng minh được một hành trình nghiệp vụ quan trọng qua những ranh giới thực sự cần xác nhận. Khi đặt E2E bên cạnh các tầng kiểm thử nhỏ hơn, chọn kịch bản theo rủi ro và duy trì dữ liệu cùng môi trường ổn định, danh mục kiểm chứng sẽ cung cấp bằng chứng xuyên suốt mà vẫn giữ được tốc độ phản hồi và khả năng bảo trì.
