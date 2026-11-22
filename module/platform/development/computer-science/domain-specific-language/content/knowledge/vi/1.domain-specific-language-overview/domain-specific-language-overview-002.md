# Vì sao cần ngôn ngữ chuyên miền?

## Bài toán: ngôn ngữ lập trình tổng quát chưa phải lúc nào cũng là cách diễn đạt tốt nhất

Một ngôn ngữ lập trình tổng quát (general-purpose language, thường viết tắt là GPL) như Java, Python hay C# có thể dùng để xây dựng rất nhiều loại phần mềm. Tính tổng quát đó đem lại sức mạnh và khả năng tái sử dụng rộng, nhưng cũng có một hệ quả: khi giải quyết một bài toán thuộc một lĩnh vực hẹp, người viết thường phải diễn đạt khái niệm của lĩnh vực ấy thông qua những cấu trúc ở mức thấp hơn.

Ví dụ, một chuyên viên dữ liệu muốn mô tả phép lọc, nhóm và tổng hợp dữ liệu. Nếu dùng các vòng lặp và cấu trúc dữ liệu thông thường, họ phải tự viết cách duyệt bản ghi, gom nhóm, xử lý giá trị thiếu và tính tổng. Phần lớn mã nguồn khi đó mô tả cách thực hiện phép tính thay vì ý nghĩa của yêu cầu. Với SQL, cùng ý định có thể được biểu đạt trực tiếp bằng `SELECT`, `WHERE`, `GROUP BY` và `HAVING`.

Khoảng cách giữa cách người làm chuyên môn suy nghĩ về vấn đề và cách ngôn ngữ lập trình buộc họ phải diễn đạt vấn đề được gọi là *khoảng cách biểu đạt* (abstraction gap hoặc semantic gap). Khi khoảng cách này lớn, mã nguồn dễ chứa nhiều chi tiết kỹ thuật phụ trợ, khó đọc đối với người hiểu nghiệp vụ và khó kiểm tra xem chương trình có đúng quy tắc của lĩnh vực hay không.

Ngôn ngữ chuyên miền (domain-specific language, DSL) được tạo ra để thu hẹp khoảng cách đó. DSL cung cấp từ vựng, cấu trúc và quy tắc phù hợp với một miền vấn đề cụ thể, chẳng hạn truy vấn dữ liệu, mô tả giao diện, cấu hình hạ tầng, xử lý văn bản hoặc mô hình hóa quy trình nghiệp vụ.

## DSL giúp diễn đạt trực tiếp khái niệm của lĩnh vực

Mỗi lĩnh vực có những khái niệm và quan hệ quen thuộc với người làm trong lĩnh vực đó. Một DSL tốt đưa những khái niệm này thành thành phần chính của ngôn ngữ.

- Trong cơ sở dữ liệu quan hệ, người dùng nghĩ về bảng, hàng, phép chiếu, phép chọn và phép kết hợp. SQL biểu đạt các thao tác đó bằng cấu trúc truy vấn.
- Trong trình bày giao diện web, người phát triển nghĩ về bộ chọn, thuộc tính, trạng thái và quy tắc hiển thị. CSS cung cấp cú pháp để mô tả các quy tắc kiểu dáng.
- Trong tìm kiếm mẫu văn bản, người dùng nghĩ về ký tự, nhóm, lựa chọn, số lần lặp và vị trí. Biểu thức chính quy (regular expression) cung cấp một ngôn ngữ ngắn gọn cho các mẫu này.
- Trong quản lý hạ tầng, người vận hành nghĩ về máy chủ, mạng, quyền truy cập và trạng thái mong muốn. Các ngôn ngữ cấu hình như HCL của Terraform mô tả tài nguyên và quan hệ giữa chúng.

Nhờ sử dụng đúng khái niệm của miền, người đọc có thể tập trung vào *điều cần đạt được* thay vì phải lần theo toàn bộ các bước triển khai. Đây là lý do DSL thường có tính khai báo (declarative): người viết nêu trạng thái, quy tắc hoặc kết quả mong muốn, còn công cụ thực thi quyết định cách đạt được kết quả đó. Không phải DSL nào cũng hoàn toàn khai báo; một số ngôn ngữ chuyên miền vẫn có cấu trúc tuần tự hoặc thủ tục khi miền bài toán cần chúng.

### Ví dụ: truy vấn dữ liệu

Giả sử cần tìm tổng doanh thu đã thanh toán theo từng khách hàng, chỉ lấy những khách hàng có tổng doanh thu trên 10 triệu đồng. SQL cho phép mô tả trực tiếp yêu cầu:

```sql
SELECT customer_id, SUM(total) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(total) > 10000000;
```

Nếu viết cùng phép xử lý bằng một ngôn ngữ tổng quát, lập trình viên thường phải mô tả thêm cách đọc dữ liệu, lọc từng đơn hàng, tạo nhóm theo khách hàng, cộng dồn doanh thu và loại bỏ nhóm không đạt điều kiện. Những bước đó hoàn toàn có thể được viết đúng và có ích trong một chương trình tổng quát; tuy nhiên, SQL làm cho cấu trúc truy vấn nổi bật hơn và để hệ quản trị cơ sở dữ liệu lựa chọn kế hoạch thực thi phù hợp.

## Giảm mã lặp và chi tiết không thuộc trọng tâm bài toán

Trong một miền nghiệp vụ, nhiều tác vụ khác nhau thường lặp lại cùng một kiểu cấu trúc. Nếu mỗi nhóm tự xây dựng cách diễn đạt bằng ngôn ngữ tổng quát, mã nguồn có thể lặp lại các thao tác chuyển đổi, kiểm tra, phân tích cú pháp và xử lý lỗi.

DSL có thể đóng gói những mẫu phổ biến thành cú pháp hoặc cấu trúc dùng chung. Ví dụ, một hệ thống xây dựng phần mềm có thể dùng Makefile để khai báo mục tiêu, phụ thuộc và lệnh cần chạy. Người phát triển mô tả quan hệ giữa các mục tiêu; công cụ xây dựng xác định thứ tự thực hiện dựa trên các quan hệ đó. Tương tự, một DSL kiểm thử có thể cung cấp cấu trúc `given`, `when`, `then` để thể hiện điều kiện ban đầu, hành động và kết quả mong đợi.

Khi các thao tác lặp được đưa vào ngôn ngữ hoặc công cụ, người dùng có thể tập trung vào phần khác biệt của từng bài toán. Điều này thường làm giảm mã phụ trợ, giúp tài liệu hóa ý định tốt hơn và tạo cơ hội chuẩn hóa cách làm giữa nhiều nhóm.

Tuy vậy, ít dòng mã hơn không tự động có nghĩa là hệ thống đơn giản hơn. Một DSL có cú pháp quá ngắn gọn, nhiều quy tắc ngầm hoặc thông báo lỗi khó hiểu có thể khiến người dùng mất nhiều thời gian hơn để học và gỡ lỗi. Mục tiêu là giảm độ phức tạp mà người dùng phải xử lý, không chỉ giảm số ký tự.

## Làm cho quy tắc miền được kiểm tra sớm và nhất quán

DSL có thể giới hạn những cách diễn đạt hợp lệ theo quy tắc của lĩnh vực. Nếu miền bài toán yêu cầu một tài nguyên phải có tên duy nhất, một trường phải thuộc một tập giá trị cho phép, hoặc một bước quy trình phải có điều kiện đầu vào nhất định, công cụ DSL có thể kiểm tra các điều kiện đó trước khi thực thi.

Các lớp kiểm tra thường gặp gồm:

1. **Kiểm tra cú pháp:** cấu trúc đầu vào có tuân theo ngữ pháp của DSL không? Ví dụ, câu lệnh có thiếu dấu phân cách hoặc dùng sai vị trí từ khóa không?
2. **Kiểm tra ngữ nghĩa:** các thành phần có hợp lệ trong ngữ cảnh không? Một tham chiếu tài nguyên có tồn tại không? Một phép toán có áp dụng được cho kiểu dữ liệu đó không?
3. **Kiểm tra quy tắc miền:** cấu hình có vi phạm chính sách của lĩnh vực không? Ví dụ, một vai trò có được phép cấp quyền quản trị hay một bước quy trình có được phép bỏ qua không?

Khi những quy tắc này được thực thi tập trung, các nhóm ít phải tự nhớ và tự cài đặt lại chúng ở nhiều nơi. DSL cũng có thể giúp phát hiện lỗi trước khi chạy chương trình hoặc trước khi thay đổi hệ thống thật. Tuy nhiên, mức độ bảo đảm phụ thuộc vào chất lượng bộ phân tích, bộ kiểm tra và quy tắc được triển khai; việc dùng một DSL không tự động làm hệ thống an toàn.

## Tạo ngôn ngữ chung giữa chuyên gia miền và người phát triển

Phần mềm thường được xây dựng bởi nhiều vai trò: chuyên gia nghiệp vụ, nhà phân tích, lập trình viên, kiểm thử viên và người vận hành. Mỗi nhóm có cách mô tả vấn đề riêng. Nếu yêu cầu chỉ được chuyển thành mã nguồn ở mức kỹ thuật, ý nghĩa nghiệp vụ có thể bị mất dần qua các bước trao đổi.

Một DSL được thiết kế với từ vựng gần với lĩnh vực có thể trở thành ngôn ngữ chung. Chuyên gia miền dễ nhận ra quy tắc họ yêu cầu; lập trình viên có thể chuyển các quy tắc đó thành hành vi có thể thực thi; kiểm thử viên có thể dùng cùng thuật ngữ để tạo trường hợp kiểm thử. Nhờ vậy, DSL có thể đóng vai trò như một đặc tả có thể đọc, kiểm tra và trong nhiều trường hợp có thể thực thi.

Ví dụ minh họa về một DSL quy tắc khuyến mãi:

```text
RULE "VIP discount"
WHEN customer.segment IS "VIP"
  AND order.total >= 2000000
THEN discount.rate = 10%
```

Đây chỉ là cú pháp giả định để minh họa. Một hệ thống thực tế cần định nghĩa rõ kiểu dữ liệu, đơn vị tiền tệ, thứ tự ưu tiên giữa các quy tắc, cách xử lý khi nhiều quy tắc cùng khớp và cách báo lỗi. Giá trị của ví dụ nằm ở việc điều kiện và kết quả được thể hiện bằng thuật ngữ gần với nghiệp vụ, thay vì bị ẩn trong nhiều nhánh `if` và phép gán.

DSL không loại bỏ nhu cầu trao đổi giữa các vai trò. Nó chỉ tạo ra một biểu diễn thống nhất hơn để các bên cùng xem xét. Từ vựng cũng phải được thống nhất; nếu tên gọi trong DSL khác với cách chuyên gia thực sự sử dụng, ngôn ngữ có thể làm tăng nhầm lẫn thay vì giảm nó.

## Tự động hóa và tái sử dụng kiến thức của miền

Khi một quy tắc được biểu diễn theo cấu trúc rõ ràng, công cụ có thể phân tích và xử lý nó theo nhiều cách. Tùy thiết kế, DSL có thể được:

- diễn giải trực tiếp bởi một interpreter;
- biên dịch thành mã của một ngôn ngữ khác;
- chuyển thành cấu hình cho một hệ thống có sẵn;
- kiểm tra tĩnh trước khi triển khai;
- dùng để sinh tài liệu, sơ đồ hoặc bộ kiểm thử;
- lưu trữ như dữ liệu để so sánh, theo dõi phiên bản và kiểm toán.

Ví dụ, cấu hình hạ tầng viết bằng một DSL có thể được công cụ phân tích để xác định tài nguyên cần tạo, cập nhật hoặc xóa. Một DSL cho quy trình có thể được dùng để hiển thị sơ đồ luồng công việc và điều phối các bước. Một DSL cho kiểm thử có thể sinh ra các trường hợp chạy tự động.

Khả năng tái sử dụng này giúp kiến thức về miền không bị phân tán hoàn toàn trong mã nguồn của từng ứng dụng. Quy tắc được định nghĩa một lần có thể được dùng bởi nhiều công cụ hoặc nhiều thành phần, miễn là chúng cùng tuân theo ngữ nghĩa đã thống nhất.

## DSL và ngôn ngữ lập trình tổng quát bổ sung cho nhau

DSL và GPL giải quyết những phạm vi khác nhau:

| Khía cạnh | Ngôn ngữ tổng quát (GPL) | Ngôn ngữ chuyên miền (DSL) |
|---|---|---|
| Phạm vi | Nhiều loại bài toán | Một miền hoặc một nhóm tác vụ hẹp |
| Khái niệm trung tâm | Cấu trúc tính toán tổng quát như biến, hàm, kiểu và điều khiển luồng | Khái niệm của miền như truy vấn, tài nguyên, kiểu dáng hoặc quy tắc nghiệp vụ |
| Khả năng biểu đạt | Rộng, có thể xây dựng nhiều loại giải pháp | Tập trung, thường ngắn gọn và rõ nghĩa trong phạm vi được thiết kế |
| Người dùng | Thường là lập trình viên hoặc kỹ sư phần mềm | Có thể gồm lập trình viên và chuyên gia miền, tùy độ phức tạp của DSL |
| Giới hạn | Có thể cần nhiều mã phụ trợ để diễn đạt tác vụ chuyên biệt | Không phù hợp khi bài toán nằm ngoài phạm vi ngôn ngữ |

Hai loại ngôn ngữ thường được dùng cùng nhau. Một ứng dụng Java có thể dùng SQL để truy vấn dữ liệu, biểu thức chính quy để tìm mẫu văn bản và một DSL cấu hình để mô tả quy tắc. Java điều phối toàn bộ ứng dụng; từng DSL diễn đạt phần công việc mà nó phù hợp.

Có hai cách triển khai DSL phổ biến:

- **DSL bên ngoài (external DSL):** có cú pháp và ngữ pháp riêng, thường cần parser hoặc công cụ đọc cú pháp. SQL, CSS và các tệp cấu hình Terraform là những ví dụ quen thuộc về ngôn ngữ có cú pháp riêng trong miền của chúng.
- **DSL nhúng (internal hoặc embedded DSL):** tận dụng cú pháp và hệ sinh thái của một ngôn ngữ chủ để tạo API có cách đọc gần với ngôn ngữ miền. Ví dụ, một thư viện Java có thể cung cấp API fluent để mô tả truy vấn hoặc quy tắc bằng các lời gọi phương thức nối tiếp.

DSL bên ngoài có thể cho phép cú pháp gần với ngôn ngữ nghiệp vụ hơn và tách biệt biểu diễn khỏi ngôn ngữ triển khai, nhưng thường cần đầu tư vào parser, công cụ hỗ trợ và thông báo lỗi. DSL nhúng có thể tận dụng trình biên dịch, IDE và thư viện của ngôn ngữ chủ, nhưng cú pháp bị giới hạn phần nào bởi ngôn ngữ đó và người dùng thường cần biết ngôn ngữ chủ.

## Khi nào việc xây dựng DSL là hợp lý?

DSL hữu ích khi một miền có các tác vụ lặp lại, khái niệm tương đối ổn định và cách diễn đạt hiện tại gây nhiều chi phí. Một số dấu hiệu cho thấy có thể cân nhắc DSL:

- Nhiều nhóm đang viết lại cùng một kiểu mã hoặc cấu hình.
- Mã nguồn chứa nhiều chi tiết kỹ thuật lặp lại, che khuất quy tắc nghiệp vụ.
- Người hiểu miền khó đọc hoặc xác nhận tính đúng đắn của mã triển khai.
- Có các quy tắc hợp lệ cần được kiểm tra nhất quán trước khi chạy.
- Cần cho phép người dùng không chuyên lập trình mô tả một phần cấu hình hoặc quy trình trong giới hạn an toàn.
- Cùng một mô hình miền cần được dùng bởi nhiều công cụ, môi trường hoặc ứng dụng.

Không nên tạo DSL chỉ vì có thể tạo ra một cú pháp mới. Nếu tác vụ hiếm gặp, quy tắc thay đổi liên tục, ngôn ngữ tổng quát đã biểu đạt đủ rõ hoặc chi phí xây dựng công cụ lớn hơn lợi ích, một thư viện, API hoặc cấu hình thông thường có thể phù hợp hơn.

## Chi phí và giới hạn cần cân nhắc

DSL giải quyết một số vấn đề bằng cách tạo thêm một lớp ngôn ngữ và công cụ. Lớp này cũng có chi phí riêng:

- **Thiết kế và bảo trì:** nhóm phát triển phải định nghĩa cú pháp, ngữ nghĩa, kiểu dữ liệu, thông báo lỗi và cách tương thích giữa các phiên bản.
- **Học và sử dụng:** người dùng phải học thêm từ vựng và quy tắc. DSL càng khác các ngôn ngữ quen thuộc, tài liệu và công cụ hỗ trợ càng quan trọng.
- **Gỡ lỗi:** khi kết quả sai, nguyên nhân có thể nằm trong tài liệu DSL, parser, bộ kiểm tra, bộ sinh mã hoặc hệ thống đích. Công cụ cần chỉ ra vị trí và nguyên nhân lỗi đủ rõ.
- **Khả năng mở rộng:** một DSL được thiết kế quá hẹp có thể khó đáp ứng nhu cầu mới; mở rộng thiếu kiểm soát có thể khiến ngôn ngữ trở nên phức tạp như một GPL.
- **Tích hợp và phụ thuộc:** DSL cần kết nối với dữ liệu, thư viện và công cụ hiện có. Nếu chỉ một công cụ hiểu định dạng riêng, việc di chuyển hệ thống có thể khó khăn.
- **Hiệu năng và bảo mật:** bộ thực thi DSL phải kiểm soát tài nguyên và quyền truy cập phù hợp. Không nên giả định rằng một cấu hình hoặc biểu thức do người dùng cung cấp luôn an toàn để thực thi.

Vì vậy, quyết định xây dựng DSL nên dựa trên lợi ích lâu dài của việc chuẩn hóa cách diễn đạt và thực thi trong miền, đồng thời tính đến toàn bộ chi phí sở hữu ngôn ngữ.

## Các bước hình thành một DSL có ích

Một quá trình thiết kế thực tế thường bắt đầu từ vấn đề lặp lại, không bắt đầu từ việc nghĩ ra cú pháp thật độc đáo.

1. **Xác định miền và người dùng:** làm rõ ai sẽ viết DSL, ai đọc nó và những tác vụ nào nằm trong phạm vi.
2. **Thu thập ví dụ thực tế:** lấy các yêu cầu, cấu hình hoặc đoạn mã hiện có để tìm các khái niệm và mẫu lặp lại.
3. **Xây dựng mô hình miền:** xác định thực thể, thuộc tính, quan hệ, thao tác và các quy tắc hợp lệ. Đây là nền tảng cho ngữ nghĩa của DSL.
4. **Viết các ví dụ trước khi chốt cú pháp:** thử biểu đạt những trường hợp thông thường, trường hợp biên và trường hợp không hợp lệ. Cách này giúp nhận ra cú pháp nào dễ đọc và phần nào còn mơ hồ.
5. **Chọn hình thức triển khai:** quyết định dùng DSL bên ngoài hay DSL nhúng, rồi xác định nó được diễn giải, biên dịch hay chuyển thành cấu hình khác.
6. **Thiết kế kiểm tra và thông báo lỗi:** phân biệt lỗi cú pháp, lỗi ngữ nghĩa và lỗi quy tắc miền; chỉ ra vị trí và cách sửa khi có thể.
7. **Tích hợp công cụ:** cân nhắc tô màu cú pháp, tự hoàn thành, định dạng, kiểm tra trước khi chạy, tài liệu và hỗ trợ trong quy trình phát triển.
8. **Quản lý thay đổi:** kiểm thử các phiên bản, xác định chính sách tương thích và cung cấp lộ trình nâng cấp khi ngữ nghĩa thay đổi.

Một DSL thành công thường có phạm vi đủ hẹp để người dùng hiểu được, nhưng đủ biểu đạt để giải quyết trọn vẹn nhóm vấn đề đã chọn. Nó giúp người dùng nói về công việc bằng khái niệm của chính lĩnh vực, đồng thời để công cụ kiểm tra và tự động hóa những quy tắc chung.
