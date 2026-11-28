# Permission theo resource

## Mục tiêu bài học

Trong chương **Least privilege**, permission theo resource là cách giới hạn quyền vào **đúng tài nguyên mà một chủ thể cần sử dụng**, thay vì cho phép một hành động trên toàn bộ hệ thống.

Trong phạm vi **Privileged Access Management (PAM)**, cách tiếp cận này áp dụng cho tài khoản quản trị, tài khoản dịch vụ và workload tác động đến hạ tầng nhạy cảm. Cần kết hợp phạm vi tài nguyên với tập hành động, thời gian, điều kiện truy cập, quản lý credential và bằng chứng sử dụng quyền.

Sau bài học, bạn có thể:

- Mô tả một quyền bằng chủ thể, hành động, tài nguyên và điều kiện.
- Phân biệt giới hạn theo resource với vị trí lưu chính sách.
- Phân tích kế thừa, wildcard, nhãn và những đường làm phạm vi quyền rộng hơn dự kiến.
- Thiết kế kiểm soát cho thao tác một tài nguyên, nhiều tài nguyên và tạo tài nguyên mới.
- Xác định bằng chứng để chứng minh một lượt dùng quyền có nằm trong phạm vi được giao hay không.

## 1. Chỉ giới hạn hành động là chưa đủ

Giả sử người trực vận hành chỉ cần khởi động lại dịch vụ A trên production.

Một quyền mô tả là “được khởi động lại dịch vụ” chưa trả lời người đó được thao tác trên:

- Dịch vụ A hay mọi dịch vụ.
- Production hay cả các môi trường khác.
- Một vùng tài nguyên hay toàn tổ chức.
- Một tài nguyên cố định hay mọi tài nguyên sẽ được tạo trong tương lai.

Hai quyền sau có cùng loại hành động nhưng khác phạm vi tác động:

| Quyền | Phạm vi |
| --- | --- |
| Khởi động lại dịch vụ A trên production | Một tài nguyên được xác định |
| Khởi động lại mọi dịch vụ trong toàn tổ chức | Nhiều tài nguyên hiện tại và có thể cả tài nguyên về sau, tùy chính sách |

Permission theo resource giúp thu hẹp chiều **“trên đối tượng nào”**. Nó không tự làm hành động trở nên an toàn. Khởi động lại đúng một dịch vụ trọng yếu vẫn có thể gây gián đoạn nếu thực hiện sai lúc hoặc quá nhiều lần.

## 2. Mô hình quyền: ai, làm gì, trên đâu, trong điều kiện nào?

Có thể diễn đạt một yêu cầu truy cập bằng bộ thông tin:

```text
Chủ thể + Hành động + Tài nguyên + Điều kiện
```

Ví dụ:

```text
Chủ thể:   danh tính quản trị của kỹ sư A
Hành động: khởi động lại dịch vụ
Tài nguyên: production / ứng dụng A / dịch vụ xử lý đơn hàng
Điều kiện: nhiệm vụ hợp lệ, quyền còn hiệu lực, luồng truy cập được chấp nhận
```

| Thành phần | Cần xác định |
| --- | --- |
| Chủ thể | Người, workload hoặc principal đang sử dụng quyền |
| Hành động | Khả năng cụ thể, gồm tác động gián tiếp nếu có |
| Tài nguyên | Định danh chuẩn, loại, phạm vi quản trị và môi trường |
| Điều kiện | Thời gian, nhiệm vụ, ngữ cảnh, trạng thái hoặc thuộc tính được hỗ trợ |

Đây là mô hình tư duy, không phải thuật toán đánh giá chính sách dùng chung cho mọi hệ thống. Quyền hiệu lực còn phụ thuộc cơ chế role, nhóm, kế thừa, chính sách tài nguyên và các giới hạn của nền tảng.

Một quyền cần đủ hẹp ở cả hành động và tài nguyên. Giới hạn vào một máy chủ nhưng vẫn cho toàn quyền quản trị máy đó có thể rộng hơn nhu cầu khởi động lại một dịch vụ.

## 3. Resource là gì trong từng môi trường?

Resource là đối tượng mà thao tác sẽ đọc, thay đổi hoặc tác động. Độ chi tiết phụ thuộc hệ thống.

| Môi trường | Resource có thể là | Điểm cần kiểm tra |
| --- | --- | --- |
| Hệ điều hành | Máy, dịch vụ, file, thư mục | Quyền trên thư mục hoặc nội dung thực thi có thể tạo tác động vượt một file |
| Cơ sở dữ liệu | Instance, database, schema, bảng, đối tượng thực thi | Quyền sở hữu, kế thừa và quyền cấp tiếp có thể mở rộng khả năng |
| Cloud | Phạm vi tài nguyên, máy ảo, dịch vụ, kho lưu trữ, khóa | Mỗi API có thể hỗ trợ mức giới hạn tài nguyên khác nhau |
| Nền tảng điều phối | Phạm vi quản lý, workload, cấu hình, bí mật | Quyền tạo hoặc sửa workload có thể cho sử dụng một danh tính khác |
| Vault | Một bí mật, nhóm bí mật, chính sách hoặc cơ chế cấp credential | Đọc một bí mật quản trị có thể mở đường đến nhiều hệ thống |
| Pipeline | Workflow, môi trường triển khai, artifact, đích phát hành | Sửa pipeline có thể ảnh hưởng tài nguyên mà danh tính phát hành quản trị |
| Công cụ PAM | Tài khoản đích, tập máy, profile phiên, tác vụ | Phạm vi trong giao diện phải phù hợp với khả năng ở hệ thống đích |

Một tên như “ứng dụng A” có thể đại diện cho nhiều tài nguyên liên quan, nhưng không có nghĩa chúng luôn nằm trong cùng một cây kế thừa quyền.

Ví dụ, dịch vụ A tham chiếu một bí mật trong vault. Bí mật đó không tự trở thành tài nguyên con của dịch vụ A trong hệ thống phân quyền. Cần kiểm tra riêng quyền trên mỗi đối tượng và quan hệ giữa chúng.

## 4. Phạm vi quyền khác với nơi đặt chính sách

Hai câu hỏi cần được tách:

1. **Quyền có giới hạn theo tài nguyên không?**
2. **Chính sách được gắn vào đâu?**

Chính sách có thể gắn với danh tính, role, tài nguyên hoặc một cấp quản trị khác. Một chính sách gắn vào danh tính vẫn có thể chỉ cho phép thao tác trên một tài nguyên. Một chính sách gắn vào tài nguyên cũng có thể cho quá nhiều chủ thể thực hiện hành động rộng.

| Thiết kế | Đánh giá |
| --- | --- |
| Role của kỹ sư A chỉ cho khởi động lại dịch vụ A | Có giới hạn tài nguyên nếu hệ thống thực thi đúng |
| Chính sách trên kho dữ liệu cho toàn bộ người dùng đọc | Gắn với tài nguyên nhưng tập chủ thể có thể quá rộng |
| Role tên “Application A Operator” nhưng cho mọi tài nguyên | Tên role không chứng minh phạm vi |
| Giao diện chỉ hiển thị ứng dụng A nhưng API chấp nhận mọi ID | Giới hạn giao diện chưa đủ để bảo vệ tài nguyên |

Không nên đồng nhất permission theo resource với một tính năng có tên “resource policy” của một sản phẩm cụ thể.

## 5. Xác định tài nguyên bằng định danh đáng tin cậy

### 5.1. Tên hiển thị không luôn đủ

Một tài nguyên có thể có:

- Tên hiển thị thay đổi được.
- Đường dẫn hoặc tên theo phạm vi.
- Định danh ổn định do hệ thống cấp.
- Môi trường, vùng hoặc đơn vị sở hữu.
- Phiên bản hoặc thế hệ tài nguyên.

Khi thiết kế policy, cần biết trường nào được hệ thống dùng để xác định đối tượng. Nếu tên có thể trùng giữa các môi trường, chỉ ghi “database-a” có thể chưa đủ.

### 5.2. Không tin trực tiếp phạm vi do client khai

Người gọi có thể gửi resource ID, tenant ID, môi trường hoặc nhãn. Hệ thống thực thi phải kiểm tra rằng chủ thể được phép hành động trên tài nguyên thực tế tương ứng.

Ví dụ, API có đường dẫn chứa `tenant_id` không nên mặc nhiên coi người dùng thuộc tenant đó chỉ vì họ gửi giá trị này. Quan hệ giữa chủ thể và phạm vi phải được xác định từ nguồn đáng tin cậy và kiểm tra phía máy chủ.

### 5.3. Chuẩn hóa trước khi quyết định quyền

Nếu hệ thống có alias, đường dẫn tương đối, liên kết hoặc nhiều tên chỉ cùng một đối tượng, kiểm soát phải dựa trên tài nguyên thực tế theo cơ chế nền tảng.

Mục tiêu là tránh việc kiểm tra quyền trên một tên nhưng sau đó thực thi trên đối tượng khác. Không nên tự xây quy tắc so khớp chuỗi đơn giản rồi coi nó tương đương với cơ chế phân giải tài nguyên của hệ thống.

### 5.4. Tài nguyên bị xóa và tạo lại

Một policy theo tên hoặc đường dẫn có thể áp dụng cho tài nguyên mới dùng lại cùng tên, tùy mô hình định danh.

Cần xác định mong muốn:

- Quyền đi theo một thực thể tài nguyên cụ thể.
- Hay quyền đi theo một vị trí hoặc tên chức năng, kể cả khi tài nguyên được thay thế.

Cả hai có thể có nhu cầu hợp lệ, nhưng phải hiểu tác động và vòng đời liên quan.

## 6. Kế thừa và những phạm vi rộng khó nhìn thấy

Một người có thể không được cấp quyền trực tiếp trên dịch vụ B nhưng vẫn có quyền từ một cấp cha hoặc nhóm.

Luồng kiểm tra khái niệm:

```text
Quyền trực tiếp trên tài nguyên
              +
Quyền qua role, nhóm hoặc quan hệ kế thừa
              +
Chính sách tài nguyên và quan hệ tin cậy
              +
Điều kiện, giới hạn và quy tắc đánh giá của nền tảng
              |
              v
Khả năng hiệu lực trên tài nguyên đích
```

Dấu cộng trong sơ đồ chỉ các nguồn cần xem xét, không khẳng định chúng được cộng quyền theo cùng một thuật toán.

Cần hỏi:

- Role được cấp ở cấp nào?
- Quyền có kế thừa xuống tài nguyên con không?
- Tài nguyên mới có tự nằm trong phạm vi không?
- Chính sách giới hạn có áp dụng cho hành động và dịch vụ đó không?
- Có đường nhận principal khác để thao tác không?
- Việc xóa một binding cục bộ có thực sự làm mất quyền không?

Thu hẹp một policy không bảo đảm thu hẹp quyền hiệu lực nếu một policy khác vẫn cho cùng khả năng. Cần đánh giá kết quả tổng thể theo đúng cơ chế nền tảng.

## 7. Wildcard và tập tài nguyên động

### 7.1. Wildcard mở rộng phạm vi theo quy tắc của hệ thống

Một mẫu tên có thể bao phủ nhiều tài nguyên hơn dự kiến, kể cả tài nguyên được tạo sau này. Cú pháp và cách so khớp khác nhau theo sản phẩm.

Trước khi dùng wildcard, cần biết:

- Phần nào của định danh được so khớp.
- Có vượt môi trường hoặc đơn vị sở hữu không.
- Ai được tạo tài nguyên có tên phù hợp.
- Quyền có tự mở rộng khi xuất hiện tài nguyên mới không.
- Có hành động nào bắt buộc dùng phạm vi rộng do giới hạn API không.

Không nên coi mọi dấu wildcard là sai. Một nhóm tài nguyên động có thể là nhu cầu hợp lệ, nhưng phải có ranh giới và quản trị vòng đời phù hợp.

### 7.2. Nhãn và thuộc tính cần được bảo vệ

Chính sách có thể dựa vào thuộc tính như ứng dụng, môi trường, đội sở hữu hoặc mức dữ liệu nếu hệ thống hỗ trợ.

Nếu chủ thể được tự sửa nhãn làm điều kiện cấp quyền, họ có thể thay đổi tập tài nguyên được phép sử dụng. Vì vậy, cần xem:

- Ai được gán và sửa thuộc tính.
- Thuộc tính đến từ nguồn nào.
- Có thể thiếu hoặc không nhất quán không.
- Điều gì xảy ra khi tài nguyên đổi chủ sở hữu hoặc môi trường.
- Thay đổi thuộc tính có được audit và áp dụng đúng thời điểm không.

Một điều kiện như “được quản trị tài nguyên có nhãn thuộc đội A” chỉ có ý nghĩa khi quyền quản lý nhãn cũng được kiểm soát.

## 8. Khi API không hỗ trợ giới hạn resource như mong muốn

Không phải hành động nào cũng hỗ trợ quyền ở mức từng đối tượng. Có hệ thống chỉ cho giới hạn một số thao tác ở phạm vi quản trị rộng hơn.

Cần xác nhận thay vì viết một policy có vẻ hẹp nhưng không được thực thi như dự kiến.

Các hướng xử lý có thể gồm:

- Dùng phạm vi quản trị nhỏ hơn nếu nền tảng hỗ trợ.
- Tách tài nguyên theo môi trường hoặc đơn vị tin cậy.
- Cung cấp giao diện tác vụ hẹp qua một dịch vụ trung gian.
- Chuyển nhu cầu sang một hành động khác có phạm vi phù hợp.
- Ghi nhận ngoại lệ, tăng kiểm soát thời gian và giám sát.

Dịch vụ trung gian không tự giải quyết vấn đề nếu nó nhận tài nguyên tùy ý và luôn thực hiện bằng credential mạnh. Chính dịch vụ phải xác thực người gọi, kiểm tra quyền trên đích thực tế và bảo vệ khả năng sửa cấu hình.

### Quyền liệt kê cũng cần đánh giá riêng

Một thao tác liệt kê có thể trả về thông tin trên phạm vi rộng, ngay cả khi thao tác đọc hoặc sửa từng tài nguyên được giới hạn.

Cần xem dữ liệu nào bị lộ qua danh sách, thông báo lỗi hoặc thông tin phụ. Lọc danh sách trên giao diện sau khi đã trả toàn bộ dữ liệu cho client không bảo vệ được dữ liệu đó.

## 9. Một thao tác có thể liên quan nhiều resource

Giới hạn tài nguyên phải bao phủ đầy đủ các đối tượng có tác động, không chỉ tài nguyên xuất hiện nổi bật nhất trong yêu cầu.

| Thao tác | Tài nguyên cần phân tích |
| --- | --- |
| Sao chép dữ liệu | Nguồn được đọc, đích được ghi, các cơ chế bảo vệ liên quan |
| Phục hồi bản sao lưu | Bản sao nguồn, môi trường đích, tài nguyên có thể bị ghi đè |
| Triển khai ứng dụng | Artifact, workload đích, danh tính thực thi, cấu hình và bí mật liên quan |
| Gắn một role hoặc danh tính | Chủ thể được gán, role, tài nguyên hoặc workload nhận quyền |
| Chuyển dữ liệu sang nơi khác | Nguồn, đích, quyền xuất dữ liệu và điều kiện được phép áp dụng |

Ví dụ, cho phép phục hồi bản sao lưu của ứng dụng A không đương nhiên nên cho phục hồi vào bất kỳ môi trường nào. Một đích ít được bảo vệ có thể tạo đường tiếp cận dữ liệu ngoài ý định.

Tương tự, quyền triển khai lên workload A cần được xem cùng khả năng chọn danh tính mạnh mà workload sẽ dùng. Giới hạn tên workload nhưng cho chọn mọi danh tính có thể tạo quyền gián tiếp.

### Tạo tài nguyên mới

Tài nguyên chưa tồn tại có thể chưa có ID cuối cùng. Quyền tạo thường cần được đánh giá trên phạm vi cha, loại tài nguyên và điều kiện tạo mà nền tảng hỗ trợ.

Cần giới hạn khả năng:

- Tạo ở môi trường nào.
- Gán danh tính hoặc quyền gì.
- Đặt thuộc tính phục vụ phân quyền thế nào.
- Tạo tài nguyên có quan hệ với dữ liệu hoặc bí mật nào.
- Kế thừa quyền và chính sách ra sao.

Quyền tạo không nên mặc nhiên trở thành quyền tạo một tài nguyên mang danh tính quản trị hoặc tự chọn nhãn để nhận thêm quyền.

## 10. Ví dụ: quyền vận hành theo resource cho ứng dụng A

Giả sử một người vận hành chỉ cần xem trạng thái và khởi động lại dịch vụ A trên production.

Một mô tả ở mức ý định có thể như sau. Đây **không phải cấu hình cho một sản phẩm cụ thể**:

```yaml
grant:
  subject: engineer-a-admin
  purpose: operate-application-a

resource_scope:
  environment: production
  resource_ids:
    - service-application-a-production

capabilities:
  - view-approved-service-status
  - restart-fixed-service

conditions:
  valid_task: required
  access_lifetime: bounded
  target_resolution: verified-by-enforcement-service

evidence:
  correlate:
    - request-id
    - subject-id
    - canonical-resource-id
    - effective-action
    - target-session-id
    - result
```

Đặc tả này cần được chuyển thành cơ chế cưỡng chế thực tế.

### Ma trận kỳ vọng

| Yêu cầu | Kỳ vọng theo nhiệm vụ |
| --- | --- |
| Xem trạng thái dịch vụ A trên production | Được phép khi đáp ứng điều kiện |
| Khởi động lại dịch vụ A trên production | Được phép khi đáp ứng điều kiện và giới hạn vận hành |
| Khởi động lại dịch vụ B | Ngoài phạm vi |
| Sửa cấu hình hoặc chương trình của dịch vụ A | Không được cấp chỉ từ nhiệm vụ vận hành này |
| Đọc bí mật quản trị toàn hệ thống | Không thuộc nhu cầu |
| Tự cấp thêm role | Không thuộc nhu cầu |
| Tiếp tục nhận quyền sau khi nhiệm vụ kết thúc | Không thuộc thời hạn đã giao |

“Không thuộc nhu cầu” là yêu cầu thiết kế, chưa phải bằng chứng hệ thống đã từ chối. Cần xem các role khác, kế thừa và đường truy cập trực tiếp để xác định quyền hiệu lực.

## 11. Kiểm tra quyền ở nơi thực thi

Một luồng khái niệm cho dịch vụ quản trị:

```text
1. Xác thực chủ thể gọi.
2. Xác định hành động thực tế.
3. Phân giải tài nguyên đích theo định danh chuẩn.
4. Thu thập ngữ cảnh từ nguồn đáng tin cậy.
5. Đánh giá quyền hiệu lực trên mọi tài nguyên liên quan.
6. Nếu được phép, thực thi trong phạm vi vừa được chấp nhận.
7. Ghi chủ thể, hành động, tài nguyên, kết quả và định danh liên kết.
```

Luồng này không thay thế cơ chế phân quyền của hệ thống đích. Nếu có nhiều lớp, cần bảo đảm chúng không tạo đường bỏ qua hoặc hiểu khác nhau về resource.

### Tránh kiểm tra trên một đối tượng rồi dùng đối tượng khác

Nếu quyền được kiểm tra trên tài nguyên A nhưng sau đó tham số, alias hoặc cấu hình làm thao tác hướng sang B, kiểm tra ban đầu không bảo vệ được B.

Cần liên kết quyết định với đích thực tế và bảo vệ quá trình phân giải. Khi tài nguyên hoặc thuộc tính có thể đổi giữa kiểm tra và thực thi, phải dùng cơ chế phù hợp của nền tảng, như kiểm tra tại thời điểm thao tác hoặc điều kiện theo phiên bản khi được hỗ trợ.

### Không dựa riêng vào giao diện

Ẩn nút hoặc lọc danh sách giúp trải nghiệm phù hợp, nhưng API và hệ thống đích vẫn phải kiểm tra quyền. Người gọi không nhất thiết dùng đúng giao diện đã thiết kế.

### Không chỉ kiểm tra lúc phát credential

Credential có thể tiếp tục tồn tại sau khi ngữ cảnh thay đổi. Cần hiểu hệ thống đích đánh giá scope, thời hạn và điều kiện vào lúc nào, cùng khả năng thu hồi hoặc ngăn sử dụng tiếp.

## 12. Kết hợp với JIT/JEA, vault và luân chuyển

### JIT: thu hẹp cửa sổ sử dụng quyền

Permission theo resource trả lời “trên tài nguyên nào”; Just-in-Time bổ sung “trong khoảng thời gian nào”.

Một quyền chỉ trên ứng dụng A nhưng tồn tại thường trực vẫn có thể rộng hơn nhu cầu của một nhiệm vụ ngắn. Khi nhiệm vụ kết thúc, cần xử lý quyền, credential và phiên theo hành vi thực tế của hệ thống.

### JEA: thu hẹp hành động

Just Enough Administration giúp giới hạn thao tác đủ cho nhiệm vụ. Cần kết hợp:

```text
Đúng chủ thể
    + Đúng hành động
    + Đúng tài nguyên
    + Đúng điều kiện và thời gian
```

Chỉ giới hạn resource nhưng giữ toàn quyền trên resource đó chưa chắc đạt least privilege. Ngược lại, hành động hẹp áp dụng toàn tổ chức cũng có thể tạo tác động diện rộng.

### Vault và credential

Nếu giao diện PAM chỉ hiển thị resource A nhưng phát credential có quyền trên A và B, người giữ credential có thể có khả năng vượt phạm vi giao diện.

Cần:

- Thu hẹp quyền ở hệ thống đích.
- Hạn chế đường sử dụng credential ngoài luồng khi phù hợp.
- Quản lý chính sách lấy bí mật theo chủ thể và nhiệm vụ.
- Kiểm soát bản sao, luân chuyển và thu hồi.
- Xác định credential đã phát hành hoặc phiên đang mở còn làm được gì.

Đưa một credential quá rộng vào vault không tự làm quyền của credential đó hẹp lại.

## 13. Bằng chứng cần giữ cho một quyết định theo resource

Một bản ghi hữu ích có thể chứa:

| Nhóm | Thông tin |
| --- | --- |
| Chủ thể | Người hoặc workload ban đầu, principal ở đích |
| Yêu cầu | Mục đích, mã nhiệm vụ, hành động được yêu cầu |
| Resource | Định danh chuẩn, loại, môi trường, phạm vi quản trị |
| Quyết định | Kết quả, nguồn chính sách hoặc phiên bản phù hợp |
| Thực thi | Hành động thực tế, tài nguyên thực tế, thời gian, kết quả |
| Vòng đời | Thời hạn quyền, credential, phiên và kết quả thu hồi |
| Thay đổi liên quan | Role, nhãn, chính sách, chủ sở hữu hoặc quan hệ tin cậy bị sửa |

Không phải nền tảng nào cũng cung cấp đầy đủ mọi trường. Cần xác định nguồn đối chiếu và khoảng trống thay vì coi một dòng “access allowed” là đủ.

Trong điều tra, cấu hình hiện tại có thể khác cấu hình tại thời điểm sự kiện. Lịch sử thay đổi quyền và thuộc tính tài nguyên giúp giải thích vì sao một hành động từng được cho phép.

Bằng chứng có thể chứa thông tin nhạy cảm. Cần giới hạn quyền xem, bảo vệ khỏi sửa hoặc xóa trái phép và tránh ghi credential đầy đủ hoặc dữ liệu không cần thiết.

## 14. Thực hành phân tích trước khi thu hẹp quyền

Một quy trình có thể gồm:

1. **Xác định nhiệm vụ.** Nêu chủ thể, hành động và kết quả cần đạt.
2. **Liệt kê tài nguyên liên quan.** Bao gồm nguồn, đích, bí mật, danh tính và phạm vi cha nếu có.
3. **Kiểm tra khả năng giới hạn của API.** Xác nhận mức resource được hỗ trợ.
4. **Đánh giá mọi đường cấp quyền.** Xem role, nhóm, kế thừa, chính sách tài nguyên và quan hệ tin cậy.
5. **Thiết kế scope và điều kiện.** Chọn định danh, thuộc tính và thời hạn phù hợp.
6. **Xác nhận tác vụ hợp lệ.** Công việc cần thiết vẫn thực hiện được.
7. **Xác nhận ranh giới.** Thao tác ngoài tài nguyên, môi trường hoặc hành động đã giao không được mở qua đường khác.
8. **Chuyển đổi và thu hồi quyền cũ.** Xử lý credential, phiên và phụ thuộc.
9. **Theo dõi thay đổi.** Rà soát khi tạo tài nguyên, đổi nhãn, chuyển đội hoặc thay workflow.

Khi xác nhận thiết kế trên hệ thống thực tế, nên xem cả tài nguyên cùng tên ở môi trường khác, tài nguyên tạo mới, quyền từ cấp cha và các thao tác có nguồn cùng đích.

Không nên chỉ dựa vào lịch sử sử dụng để xóa mọi quyền chưa xuất hiện trong một khoảng quan sát. Công việc theo chu kỳ, phục hồi và sự cố hiếm gặp có thể chưa phát sinh. Cần kết hợp dữ liệu sử dụng với yêu cầu nghiệp vụ và chủ sở hữu quyền.

## 15. Tình huống tự đánh giá

Một đội có role “Application A Operator” với thiết kế sau:

- Giao diện chỉ hiển thị ứng dụng A.
- Credential đích vẫn có quyền quản trị mọi ứng dụng trong phạm vi production.
- API vận hành nhận resource ID từ client nhưng không kiểm tra quyền trên ID đó.
- Tài nguyên có nhãn `team-a` được đưa vào phạm vi; người vận hành tự sửa được nhãn.
- Quyền hết hạn trong PAM, nhưng phiên API có vòng đời riêng chưa được xử lý.

### Phân tích

**Tên role và giao diện chưa tạo scope thực tế:** credential vẫn có quyền rộng.

**Thiếu kiểm tra đích:** resource ID từ client chưa được đối chiếu với quyền của chủ thể.

**Thuộc tính có thể tự thay:** chính người dùng quyết định tài nguyên nào thỏa điều kiện cấp quyền.

**Vòng đời không đồng nhất:** hết hạn ở PAM chưa chứng minh phiên đích đã mất khả năng thao tác.

### Hướng cải thiện

- Giới hạn credential và quyền hiệu lực vào tài nguyên cần thiết khi nền tảng hỗ trợ.
- Kiểm tra hành động trên định danh chuẩn ở nơi thực thi.
- Bảo vệ quyền gán và sửa thuộc tính dùng trong policy.
- Kiểm kê quyền từ nhóm, cấp cha và principal khác.
- Xác định cách xử lý credential cùng phiên khi kết thúc nhiệm vụ.
- Liên kết bằng chứng giữa yêu cầu, quyết định và resource thực tế.
- Nếu API không hỗ trợ scope cần thiết, thiết kế ranh giới thay thế và ghi nhận giới hạn rõ ràng.

Đổi tên role hoặc thêm bộ lọc giao diện không xử lý được các đường quyền rộng ở phía dưới.

## 16. Những điểm cần ghi nhớ

- Permission theo resource giới hạn đối tượng bị tác động, bổ sung cho giới hạn hành động và thời gian.
- Phạm vi quyền khác với nơi đặt policy. Cần đánh giá quyền hiệu lực thay vì chỉ đọc tên role.
- Định danh, kế thừa, wildcard, nhãn và quyền tạo tài nguyên đều có thể làm phạm vi thay đổi.
- Một thao tác có thể liên quan nhiều resource; phải xem cả nguồn, đích và những danh tính hoặc bí mật được sử dụng.
- Kiểm tra phải gắn với tài nguyên thực tế tại nơi thực thi, không chỉ giao diện hoặc tham số do client khai.
- Thiết kế PAM cần chứng minh được **chủ thể nào được thực hiện hành động nào, trên resource nào, trong điều kiện gì và quyền đã được thu hồi ra sao**.