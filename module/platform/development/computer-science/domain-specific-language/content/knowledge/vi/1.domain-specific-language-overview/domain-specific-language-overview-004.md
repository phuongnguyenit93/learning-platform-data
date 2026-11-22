# DSL khác ngôn ngữ đa dụng

Trong khoa học máy tính, một ngôn ngữ lập trình có thể được thiết kế để giải quyết nhiều loại bài toán, hoặc tập trung diễn đạt một nhóm công việc cụ thể. Hai hướng thiết kế này thường được gọi là **ngôn ngữ đa dụng** (*General-Purpose Language – GPL*) và **ngôn ngữ chuyên biệt theo miền** (*Domain-Specific Language – DSL*).

Điểm khác biệt cốt lõi nằm ở **phạm vi và mục đích thiết kế**. Ngôn ngữ đa dụng cung cấp các công cụ tổng quát để xây dựng nhiều loại chương trình. DSL cung cấp cách diễn đạt gần với khái niệm của một lĩnh vực, giúp người dùng mô tả công việc trong lĩnh vực đó ngắn gọn và rõ nghĩa hơn.

## 1. Ngôn ngữ đa dụng là gì?

Ngôn ngữ đa dụng được thiết kế để có thể sử dụng trong nhiều lĩnh vực khác nhau. Với một ngôn ngữ như Python, Java, C# hoặc C++, lập trình viên có thể xây dựng ứng dụng web, xử lý dữ liệu, viết công cụ dòng lệnh, phát triển trò chơi, điều khiển thiết bị hoặc triển khai thuật toán.

Để hỗ trợ phạm vi rộng, ngôn ngữ đa dụng thường cung cấp một bộ cấu trúc tổng quát, chẳng hạn:

- Biến và kiểu dữ liệu để biểu diễn thông tin.
- Câu lệnh điều kiện và vòng lặp để điều khiển luồng thực thi.
- Hàm, lớp và mô-đun để tổ chức chương trình.
- Cấu trúc dữ liệu và cơ chế xử lý lỗi.
- Thư viện và giao diện để kết nối với hệ điều hành, mạng, cơ sở dữ liệu hoặc dịch vụ khác.

Những thành phần này không gắn chặt với một lĩnh vực duy nhất. Lập trình viên kết hợp chúng theo cách phù hợp với bài toán đang giải quyết.

Ví dụ, Python có thể dùng để đọc tệp, gọi API, phân tích dữ liệu hoặc xây dựng máy chủ. Bản thân ngôn ngữ không giới hạn người viết vào một trong các công việc đó.

## 2. DSL là gì?

DSL là ngôn ngữ có cú pháp, khái niệm và quy tắc được thiết kế xoay quanh một **miền vấn đề** (*domain*) cụ thể. Miền đó có thể là truy vấn dữ liệu, định dạng tài liệu, mô tả giao diện, cấu hình hạ tầng, xây dựng phần mềm hoặc kiểm thử.

Một số ví dụ thường gặp:

| DSL | Miền sử dụng | Cách diễn đạt chính |
|---|---|---|
| SQL | Truy vấn và thao tác dữ liệu quan hệ | Chọn bảng, cột, điều kiện và cách nhóm hoặc sắp xếp dữ liệu |
| CSS | Trình bày giao diện web | Chọn phần tử và khai báo quy tắc hiển thị |
| Regular expressions (regex) | Tìm kiếm và kiểm tra mẫu văn bản | Mô tả chuỗi ký tự cần khớp |
| Makefile | Tự động hóa quá trình build | Khai báo mục tiêu, phụ thuộc và lệnh cần chạy |
| HCL của Terraform | Mô tả hạ tầng | Khai báo tài nguyên và cấu hình mong muốn |

Các ví dụ này dùng những cách viết khác nhau, nhưng đều có từ vựng và cấu trúc gắn với một công việc nhất định. Người dùng diễn đạt ý định trong miền đó thay vì phải tự xây dựng mọi bước bằng các cấu trúc tổng quát.

Chẳng hạn, trong SQL, `SELECT`, `FROM`, `WHERE` và `ORDER BY` trực tiếp thể hiện các thao tác truy vấn. Người đọc có thể nhận ra mục đích của câu lệnh mà không cần xem một vòng lặp duyệt từng bản ghi.

## 3. So sánh DSL và ngôn ngữ đa dụng

| Tiêu chí | DSL | Ngôn ngữ đa dụng |
|---|---|---|
| Phạm vi | Tập trung vào một miền hoặc một nhóm tác vụ liên quan | Hướng đến nhiều loại miền và bài toán |
| Mục tiêu thiết kế | Diễn đạt khái niệm của miền bằng cách tự nhiên, ngắn gọn và có quy tắc | Cung cấp nền tảng tổng quát để xây dựng nhiều loại phần mềm |
| Từ vựng | Thường dùng thuật ngữ và khái niệm của miền | Dùng khái niệm lập trình tổng quát như biến, hàm, kiểu và luồng điều khiển |
| Cách mô tả | Có thể tập trung mô tả kết quả, quy tắc, cấu hình hoặc mô hình | Có thể mô tả cả thuật toán, trạng thái và quy trình thực thi tùy ý |
| Độ linh hoạt | Thuận tiện trong phạm vi được thiết kế; có thể khó diễn đạt việc nằm ngoài miền | Linh hoạt hơn khi giải quyết bài toán mới hoặc kết hợp nhiều lĩnh vực |
| Người sử dụng | Có thể hướng đến chuyên gia miền, lập trình viên hoặc cả hai | Chủ yếu hướng đến người xây dựng và bảo trì phần mềm |
| Công cụ thực thi | Thường cần bộ phân tích, trình thông dịch, engine hoặc công cụ riêng của miền | Thường có compiler hoặc runtime tổng quát cùng hệ sinh thái thư viện |

Đây là xu hướng thiết kế, không phải danh sách quy tắc tuyệt đối. Một DSL có thể có tính năng phức tạp và một ngôn ngữ đa dụng vẫn có thể cung cấp thư viện giúp viết mã theo phong cách chuyên biệt.

### 3.1. Phạm vi và mức độ biểu đạt

Ngôn ngữ đa dụng cố gắng cung cấp những khối xây dựng có thể kết hợp để giải quyết nhiều loại vấn đề. Đổi lại, người viết thường phải tự kết hợp nhiều cấu trúc để diễn đạt một thao tác thuộc lĩnh vực cụ thể.

DSL thu hẹp phạm vi để làm cho các thao tác trong miền trở nên trực tiếp. Một câu truy vấn SQL có thể diễn đạt việc lọc, chọn cột và sắp xếp dữ liệu trong một cấu trúc ngắn. Một biểu thức regex có thể mô tả mẫu văn bản bằng các ký hiệu dành riêng cho việc khớp chuỗi.

Sự ngắn gọn này có lợi khi công việc lặp lại và khái niệm của miền đã rõ ràng. Tuy nhiên, nếu yêu cầu nằm ngoài phạm vi DSL, người dùng có thể phải kết hợp DSL với một ngôn ngữ khác hoặc chuyển phần xử lý đó sang chương trình đa dụng.

### 3.2. Từ vựng và mức độ trừu tượng

DSL thường đặt tên cho các khái niệm mà người làm trong lĩnh vực đã quen thuộc. Ví dụ, SQL sử dụng các khái niệm bảng, hàng, cột và phép nối. CSS sử dụng bộ chọn, thuộc tính và giá trị để mô tả cách trình bày.

Ngôn ngữ đa dụng cung cấp các khái niệm ở mức lập trình. Người viết có thể cần biểu diễn một khái niệm nghiệp vụ bằng kiểu dữ liệu, hàm, lớp hoặc cấu trúc điều khiển. Cách này có khả năng tùy biến cao, nhưng đôi khi tạo ra khoảng cách giữa cách chuyên gia miền suy nghĩ và cách chương trình được viết.

### 3.3. Quyền quyết định cách thực thi

Một DSL có thể cho phép người dùng mô tả **muốn điều gì** để engine của miền quyết định **thực hiện như thế nào**. SQL là ví dụ điển hình: câu truy vấn mô tả dữ liệu cần lấy; hệ quản trị cơ sở dữ liệu có thể chọn kế hoạch thực thi phù hợp.

Trong ngôn ngữ đa dụng, lập trình viên thường có nhiều quyền kiểm soát trực tiếp hơn đối với các bước xử lý, thứ tự thao tác và trạng thái của chương trình. Đây là một xu hướng chứ không phải ranh giới cứng: ngôn ngữ đa dụng cũng có thư viện khai báo, còn DSL có thể cho phép mô tả quy trình thực thi chi tiết.

## 4. Một bài toán, hai cách diễn đạt

Giả sử cần lấy tên và mức lương của nhân viên thuộc phòng ban `Engineering`, có mức lương lớn hơn 50.000, sau đó sắp xếp theo lương giảm dần.

Với SQL, yêu cầu có thể được viết như sau:

```sql
SELECT name, salary
FROM employees
WHERE department = 'Engineering'
  AND salary > 50000
ORDER BY salary DESC;
```

Câu lệnh sử dụng trực tiếp các khái niệm của truy vấn dữ liệu: bảng nguồn, điều kiện lọc, cột cần lấy và thứ tự kết quả.

Với Python, có thể viết một cách tổng quát hơn như sau:

```python
result = sorted(
    (
        {"name": employee["name"], "salary": employee["salary"]}
        for employee in employees
        if employee["department"] == "Engineering"
        and employee["salary"] > 50000
    ),
    key=lambda employee: employee["salary"],
    reverse=True,
)
```

Đoạn Python thể hiện cách duyệt dữ liệu, kiểm tra điều kiện, tạo bản ghi kết quả và sắp xếp danh sách. Python có thể thực hiện rất nhiều công việc khác ngoài truy vấn này, nên các cấu trúc của nó không bị giới hạn vào miền cơ sở dữ liệu.

Hai đoạn mã diễn đạt cùng một yêu cầu ở hai mức trừu tượng khác nhau. SQL cung cấp cú pháp chuyên cho truy vấn và giao việc tối ưu thực thi cho hệ quản trị cơ sở dữ liệu. Python cung cấp các cấu trúc tổng quát để lập trình viên tổ chức các bước xử lý. Trong một ứng dụng thực tế, Python hoàn toàn có thể gửi câu SQL đến cơ sở dữ liệu rồi tiếp tục xử lý kết quả.

## 5. DSL độc lập và DSL nhúng

DSL có thể được triển khai theo nhiều cách. Hai hình thức thường được nhắc đến là DSL độc lập (*external DSL*) và DSL nhúng (*embedded/internal DSL*).

**DSL độc lập** có cú pháp riêng và thường được phân tích hoặc thực thi bởi một công cụ chuyên biệt. SQL, CSS, regex và cấu hình Terraform là những ví dụ quen thuộc. Tệp DSL có thể được viết, kiểm tra và chạy bằng công cụ của chính miền đó.

**DSL nhúng** được biểu diễn bên trong một ngôn ngữ chủ (*host language*), thường thông qua cú pháp, hàm, đối tượng hoặc API của ngôn ngữ chủ. Ví dụ, một thư viện có thể cung cấp các lời gọi hàm có tên gần với khái niệm nghiệp vụ để người dùng mô tả truy vấn, tuyến đường web hoặc kịch bản kiểm thử. Vì dùng chung môi trường của ngôn ngữ chủ, DSL nhúng thường tận dụng được compiler, kiểu dữ liệu, thư viện và công cụ gỡ lỗi sẵn có.

Ranh giới giữa hai hình thức này đôi khi không hoàn toàn rõ. Một DSL nhúng có thể trông giống ngôn ngữ riêng, trong khi một DSL độc lập vẫn có thể gọi hoặc được gọi từ chương trình viết bằng ngôn ngữ đa dụng.

## 6. Vì sao cần DSL?

DSL có ích khi một miền có các khái niệm ổn định và người dùng thường xuyên phải mô tả cùng một loại quy tắc hoặc thao tác.

**Lợi ích thường gặp:**

- **Diễn đạt đúng ngôn ngữ của miền:** tên lệnh và cấu trúc gần với cách chuyên gia mô tả công việc.
- **Giảm mã lặp:** một cấu trúc chuyên biệt có thể thay thế nhiều bước xử lý tổng quát.
- **Dễ đọc và trao đổi:** người hiểu miền có thể đọc hoặc thảo luận quy tắc mà không cần theo dõi toàn bộ chi tiết triển khai.
- **Kiểm tra theo ngữ cảnh:** công cụ có thể phát hiện cấu hình hoặc câu lệnh không hợp lệ dựa trên quy tắc của miền.
- **Giới hạn thao tác:** DSL có thể chỉ cho phép những hành động cần thiết, giúp cấu hình dễ kiểm soát hơn.

**Chi phí và giới hạn cần cân nhắc:**

- **Phạm vi hẹp:** yêu cầu mới nằm ngoài miền có thể khó biểu đạt.
- **Chi phí xây dựng công cụ:** một DSL riêng có thể cần parser, validator, runtime, tài liệu và môi trường phát triển.
- **Đường học tập riêng:** người dùng vẫn phải hiểu cú pháp, quy tắc và công cụ của DSL.
- **Tích hợp và gỡ lỗi:** cần cơ chế kết nối với ngôn ngữ, hệ thống và quy trình hiện có.
- **Phụ thuộc hệ sinh thái:** chất lượng công cụ, khả năng tương thích và hỗ trợ lâu dài ảnh hưởng trực tiếp đến việc sử dụng DSL.

Vì vậy, DSL không tự động làm cho hệ thống đơn giản hơn. Giá trị của nó phụ thuộc vào việc lợi ích khi diễn đạt công việc trong miền có lớn hơn chi phí thiết kế, duy trì và tích hợp hay không.

## 7. Khi nào nên dùng DSL, khi nào nên dùng ngôn ngữ đa dụng?

DSL phù hợp khi công việc có phạm vi tương đối rõ, lặp lại thường xuyên và có một bộ khái niệm chung mà người dùng cần diễn đạt. Ví dụ, truy vấn dữ liệu thường dùng SQL; mô tả kiểu hiển thị trang web thường dùng CSS; mô tả tài nguyên hạ tầng có thể dùng HCL của Terraform.

Ngôn ngữ đa dụng phù hợp khi cần xây dựng thuật toán mới, điều phối nhiều hệ thống, xử lý logic phức tạp hoặc kết hợp nhiều lĩnh vực. Python, Java hay C# có thể đóng vai trò ngôn ngữ nền để xây dựng ứng dụng, đồng thời gọi các DSL chuyên biệt khi cần.

Trong nhiều hệ thống, lựa chọn tốt là **kết hợp cả hai**. Chẳng hạn, một ứng dụng viết bằng Java có thể dùng SQL để truy vấn dữ liệu; một công cụ viết bằng Python có thể đọc cấu hình, gọi API và sinh tệp CSS. Ngôn ngữ đa dụng điều phối toàn bộ chương trình, còn DSL diễn đạt những phần có quy tắc chuyên biệt.

Khi quyết định tạo DSL mới, có thể cân nhắc các câu hỏi sau:

1. Miền vấn đề có đủ rõ ràng và ổn định để xác định từ vựng, cú pháp và quy tắc riêng không?
2. Có nhiều người cần mô tả cùng loại thao tác mà không muốn viết mã tổng quát không?
3. DSL có giúp giảm lỗi hoặc làm quy tắc dễ đọc hơn một API hay thư viện thông thường không?
4. Nhóm có thể duy trì parser, validator, tài liệu, công cụ và khả năng tương thích theo thời gian không?

Nếu một thư viện hoặc cấu hình đơn giản đã giải quyết tốt nhu cầu, việc tạo thêm một ngôn ngữ có thể không đem lại đủ lợi ích.

## 8. Những hiểu nhầm thường gặp

**DSL không nhất thiết phải ngắn hoặc dễ học.** Một DSL có cú pháp phức tạp, nhiều quy tắc và công cụ riêng. Mục tiêu của nó là phù hợp với miền, không phải luôn giảm số ký tự hay độ khó.

**DSL không nhất thiết chỉ dành cho người không biết lập trình.** Nhiều DSL được lập trình viên sử dụng hàng ngày để truy vấn dữ liệu, cấu hình build, viết kiểm thử hoặc mô tả hạ tầng.

**Ngôn ngữ đa dụng vẫn có thể chuyên sâu trong một dự án.** Việc một nhóm chỉ dùng Python để xử lý dữ liệu không biến Python thành DSL; phạm vi thiết kế của Python vẫn là đa dụng.

**Ranh giới DSL và GPL không chỉ dựa vào sức mạnh tính toán.** Một DSL có thể hỗ trợ biểu thức và logic rất mạnh. Điều quyết định là ngôn ngữ được thiết kế xoay quanh miền cụ thể hay hướng đến nhiều miền khác nhau.

**Một hệ thống có thể dùng nhiều ngôn ngữ.** Việc kết hợp DSL với ngôn ngữ đa dụng là cách làm phổ biến, vì mỗi loại ngôn ngữ đảm nhận phần việc mà nó diễn đạt hiệu quả nhất.

## 9. Ghi nhớ

- Ngôn ngữ đa dụng cung cấp các cấu trúc tổng quát để xây dựng nhiều loại phần mềm.
- DSL tập trung vào một miền và cung cấp cú pháp, từ vựng hoặc mô hình phù hợp với công việc trong miền đó.
- DSL thường giúp quy tắc chuyên biệt ngắn gọn, dễ đọc và dễ kiểm tra hơn; đổi lại, phạm vi sử dụng và hệ sinh thái có thể hẹp hơn.
- Hai loại ngôn ngữ bổ sung cho nhau. Một ứng dụng có thể dùng ngôn ngữ đa dụng để điều phối và DSL để mô tả các tác vụ chuyên biệt.

## 10. Câu hỏi tự kiểm tra

1. Vì sao Python được xem là ngôn ngữ đa dụng dù có thể được dùng chủ yếu cho phân tích dữ liệu trong một dự án?
2. SQL thể hiện tính chuyên biệt theo miền qua những từ khóa và khái niệm nào?
3. Nêu một lợi ích và một chi phí khi xây dựng DSL riêng cho một lĩnh vực.
4. Trong một ứng dụng quản lý nhân viên, phần nào có thể dùng ngôn ngữ đa dụng và phần nào có thể dùng DSL?
5. Vì sao việc kết hợp DSL với ngôn ngữ đa dụng thường hữu ích hơn việc cố dùng duy nhất một loại ngôn ngữ cho mọi công việc?
