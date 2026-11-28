# Service account privilege

## 1. Đặc quyền của service account là gì?

Một service account là danh tính mà ứng dụng, tác vụ tự động hoặc thành phần hạ tầng sử dụng khi tương tác với hệ thống khác. **Service account privilege** là khả năng mà danh tính đó được phép thực hiện đối với tài nguyên, bao gồm cả quyền nghiệp vụ và các quyền có thể thay đổi ranh giới bảo mật.

Ví dụ, `invoice-exporter-prod` có thể cần đọc hóa đơn và ghi tệp xuất vào một vùng lưu trữ. Nó không mặc nhiên cần quyền xóa hóa đơn, tạo tài khoản, thay chính sách IAM hoặc nhận danh tính của dịch vụ khác.

Trong nhiều tài liệu, privilege được dùng gần nghĩa với permission. Tuy nhiên, **privileged service account** thường chỉ account có quyền nhạy cảm hoặc phạm vi tác động lớn, chẳng hạn quản trị dữ liệu, thay đổi phân quyền, triển khai phần mềm hoặc vận hành hạ tầng. Không phải mọi service account đều cần trở thành tài khoản đặc quyền.

Cần phân biệt ba thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Identity | Account đang đại diện cho bên nào | `invoice-exporter-prod` |
| Credential | Bằng chứng dùng để xác thực account | Token hoặc chứng thư phù hợp |
| Privilege | Những thao tác account được phép thực hiện | Đọc hóa đơn thuộc tenant được chỉ định |

Token có thời hạn ngắn vẫn có thể mang quyền rất rộng. Ngược lại, một credential được lưu cẩn thận không làm cho một tập quyền quản trị dư thừa trở nên hợp lý. Quản lý credential và quản lý đặc quyền phải được thực hiện đồng thời.

## 2. Mô tả quyền bằng hành động, tài nguyên và điều kiện

Một yêu cầu cấp quyền có ích phải cụ thể hơn câu “service cần truy cập hệ thống kế toán”. Có thể mô tả nó bằng các câu hỏi:

1. Principal nào cần quyền?
2. Hành động nào cần được thực hiện?
3. Hành động áp dụng cho tài nguyên hoặc tập tài nguyên nào?
4. Quyền chỉ hợp lệ trong điều kiện nào?
5. Nhu cầu kéo dài đến khi nào và ai chịu trách nhiệm?

Ví dụ:

```text
Principal: invoice-exporter-prod
Hành động: đọc hóa đơn đã chốt
Tài nguyên: hóa đơn của tenant-42
Điều kiện: yêu cầu đi đến API hóa đơn production được chỉ định
Mục đích: xuất báo cáo cuối ngày
Chủ sở hữu: nhóm vận hành báo cáo
```

Phạm vi tài nguyên phải được thực thi bởi bên có trách nhiệm phân quyền. Đặt một đường dẫn có tên `tenant-42` trong cấu hình ứng dụng không chứng minh account đã bị giới hạn vào tenant đó. Nếu API hoặc chính sách tài nguyên vẫn cho phép account đọc mọi tenant, quyền hiệu lực vẫn rộng.

Điều kiện cũng chỉ có giá trị khi hệ thống hỗ trợ và kiểm tra nó bằng nguồn thông tin đáng tin cậy. Một header do bên gọi tự khai như `environment=production` không tự tạo thành bằng chứng về môi trường chạy workload.

## 3. Quyền hiệu lực có thể rộng hơn quyền nhìn thấy trên account

Service account có thể nhận quyền từ nhiều nguồn: role được gán trực tiếp, group, phạm vi cha, chính sách trên tài nguyên, liên kết danh tính hoặc cơ chế ủy quyền. Ngoài ra có thể tồn tại giới hạn tổ chức, chính sách phiên, điều kiện thời gian và các quy tắc từ chối.

Không nên dùng một công thức cộng quyền đơn giản cho mọi nền tảng. Cách kết hợp policy, thứ tự đánh giá và hiệu lực của deny phụ thuộc mô hình IAM cụ thể. Khi đánh giá quyền hiệu lực, cần xem toàn bộ các nguồn cấp và các giới hạn có liên quan theo đúng ngữ nghĩa của hệ thống.

| Nguồn hoặc giới hạn | Câu hỏi cần kiểm tra |
| --- | --- |
| Role gán trực tiếp | Role chứa chính xác những thao tác nào? |
| Group hoặc quan hệ thành viên | Account có nhận quyền qua group không? Ai được đổi thành viên? |
| Phạm vi cha | Quyền có được kế thừa từ tổ chức, project hoặc namespace không? |
| Chính sách tài nguyên | Tài nguyên có cấp thêm quyền cho account hoặc một tập principal rộng hơn không? |
| Điều kiện và giới hạn | Điều kiện nào thực sự được đánh giá trên từng yêu cầu? |
| Credential hoặc phiên | Quyền được tra cứu lúc gọi hay đã được phản ánh trong credential? |
| Cache và đồng bộ policy | Sau thay đổi, bao lâu bên thực thi mới nhìn thấy trạng thái mới? |

Tên role không phải bằng chứng đủ về mức an toàn. Một role có tên `Reader` có thể cho phép đọc secret, dữ liệu cá nhân hoặc cấu hình nhạy cảm. Đọc được dữ liệu có giá trị cao vẫn là một quyền nhạy cảm, dù không có thao tác ghi.

Khi một role chuẩn quá rộng, có thể cân nhắc role tùy chỉnh nếu nền tảng hỗ trợ và tổ chức có khả năng quản lý vòng đời của nó. Role tùy chỉnh cũng cần được theo dõi khi API, nghiệp vụ hoặc cấu trúc tài nguyên thay đổi.

## 4. Tách quyền nghiệp vụ khỏi quyền quản trị

### Quyền trên dữ liệu và chức năng nghiệp vụ

Đây là các thao tác như đọc hóa đơn, cập nhật trạng thái giao hàng, ghi đối tượng vào kho lưu trữ hoặc xử lý một hàng đợi. Chúng thường gắn trực tiếp với công việc của workload.

Ngay trong nhóm này, cần phân biệt đọc, tạo, cập nhật và xóa. Một job xuất dữ liệu không nên nhận luôn quyền xóa dữ liệu nguồn chỉ vì một role dựng sẵn gộp cả hai.

### Quyền trên cơ chế quản lý

Các quyền quản trị có thể bao gồm tạo credential, sửa chính sách truy cập, gán role, sửa nguồn trust, triển khai mã, thay cấu hình hoặc gắn danh tính vào workload.

Những quyền này có thể cho phép thay đổi chủ thể nào được truy cập tài nguyên, thay vì chỉ thực hiện một thao tác dữ liệu cụ thể. Vì vậy, chúng cần được đánh giá như một phần của ranh giới đặc quyền.

Ví dụ, một account không cần đọc trực tiếp cơ sở dữ liệu nhưng có quyền thay mã của dịch vụ đang sở hữu quyền đọc cơ sở dữ liệu có thể tạo ra một đường truy cập gián tiếp. Cần biết mã mới có được thực thi tự động không, quá trình triển khai có kiểm soát gì và dịch vụ chạy dưới danh tính nào.

Sự tách biệt này cũng xuất hiện trong vận hành: một account dùng khi triển khai có thể cần thay tài nguyên, trong khi account dùng lúc ứng dụng chạy chỉ cần thực hiện nghiệp vụ. Không nên mang toàn bộ quyền triển khai vào danh tính runtime chỉ vì chúng thuộc cùng một ứng dụng.

## 5. Đặc quyền gián tiếp và khả năng đại diện cho account

Đánh giá service account privilege cần xem cả hai hướng:

- Service account có thể làm gì đối với tài nguyên hoặc danh tính khác?
- Những bên nào có thể hành động với tư cách service account đó?

Một account có quyền hẹp vẫn có thể là điểm trung chuyển đến account mạnh hơn nếu nó được phép impersonate, tạo credential hoặc thay chính sách trust của account mạnh hơn.

Ngược lại, một lập trình viên không có quyền đọc dữ liệu production trực tiếp có thể vẫn tiếp cận dữ liệu nếu người đó được triển khai mã tùy ý chạy dưới một service account có quyền đọc dữ liệu đó.

```mermaid
flowchart LR
    U[Danh tính triển khai] -->|Có quyền đưa mã vào workload| W[Workload production]
    W -->|Được gắn và sử dụng danh tính| S[Service account]
    S -->|Được đọc secret xác thực| K[Secret cơ sở dữ liệu]
    K -->|Credential được DB chấp nhận| D[Dữ liệu nhạy cảm]
```

Sơ đồ mô tả một đường quyền có điều kiện, không khẳng định mọi quyền triển khai đều cho phép đọc mọi dữ liệu. Đường này chỉ tồn tại khi các cạnh tương ứng thực sự được phép và không bị các kiểm soát khác ngăn chặn. Nó cho thấy tại sao chỉ kiểm tra role trên cơ sở dữ liệu chưa đủ để kết luận người triển khai không thể truy cập dữ liệu.

Các khả năng cần đặc biệt chú ý gồm:

1. Tạo hoặc lấy credential đại diện cho account khác.
2. Thay role, thành viên group hoặc chính sách tài nguyên.
3. Thay danh tính gắn với workload, hoặc chạy mã dưới danh tính mạnh hơn.
4. Sửa pipeline, mã nguồn, artifact hoặc cấu hình sẽ được một thành phần đặc quyền thực thi.
5. Đọc secret có thể mở ra quyền ở hệ thống khác.

Không chỉ tổng số permission, mà khả năng kết hợp chúng mới quyết định mức tác động. Quyền đọc một secret cộng với khả năng kết nối tới hệ thống đích có thể quan trọng hơn nhiều quyền đọc metadata thông thường.

## 6. Áp dụng nguyên tắc ít quyền nhất

Nguyên tắc ít quyền nhất là cấp đủ quyền để thực hiện công việc đã được xác định, trong phạm vi và thời gian cần thiết. Nó không có nghĩa cấp một role quản trị cho nhanh rồi trông chờ ứng dụng tự sử dụng cẩn thận.

### Bắt đầu từ luồng nghiệp vụ

Với job xuất hóa đơn, có thể liệt kê:

| Bước nghiệp vụ | Quyền dự kiến | Phạm vi cần giới hạn |
| --- | --- | --- |
| Tìm các hóa đơn đủ điều kiện xuất | Liệt kê hoặc tìm kiếm hóa đơn | Tenant và trạng thái cần xử lý |
| Đọc nội dung hóa đơn | Đọc hóa đơn | Các hóa đơn thuộc phạm vi được phép |
| Ghi tệp xuất | Tạo đối tượng | Vùng lưu trữ đầu ra được chỉ định |
| Gửi trạng thái chạy | Ghi sự kiện hoặc metric được phép | Điểm nhận quan sát của dịch vụ |

Quyền liệt kê không luôn đồng nghĩa quyền đọc từng đối tượng, và quyền tạo không luôn đồng nghĩa quyền ghi đè hoặc xóa. Phải đối chiếu mô hình quyền thực tế của API.

Ngoài đường chạy thành công, cần xem các luồng khởi động, lấy cấu hình, xử lý lỗi, retry, khôi phục và tác vụ định kỳ. Tuy nhiên, “có thể một ngày nào đó cần” không phải lý do đủ để giữ quyền quản trị vĩnh viễn.

### Giới hạn phạm vi theo ranh giới có ý nghĩa

Có thể tách account theo môi trường, nhóm dịch vụ, mức đặc quyền hoặc tenant khi yêu cầu cô lập cần đến. Không nhất thiết tạo một account cho mọi hàm; điều quan trọng là account dùng chung không làm mất một ranh giới tin cậy cần bảo vệ.

Nếu hai workload có nhu cầu quyền khác nhau rõ rệt, dùng một account chung sẽ khiến mỗi workload thừa hưởng tập quyền phục vụ cả hai. Tách danh tính giúp giảm quyền dư thừa và cải thiện truy vết.

### Giới hạn quyền nhạy cảm theo thời gian

Một công việc bảo trì có thể cần đặc quyền trong một khoảng thời gian ngắn. Khi nền tảng và quy trình hỗ trợ, có thể cấp quyền tạm thời với điều kiện kích hoạt, thời điểm kết thúc và bằng chứng sử dụng.

Tác vụ đặc quyền nên được tách khỏi tiến trình phục vụ thông thường nếu có thể. Một web service chạy liên tục không cần giữ quyền sửa schema chỉ vì quá trình triển khai thỉnh thoảng thực hiện migration.

Quyền tạm thời vẫn cần đúng phạm vi. Cấp quyền quản trị quá rộng trong mười phút có thể đủ để tạo một đường truy cập dài hạn khác nếu không kiểm soát các thao tác tạo credential và thay chính sách.

## 7. Lập hồ sơ quyền trước khi cấp

Một hồ sơ cấp quyền giúp người duyệt hiểu tại sao quyền tồn tại và giúp người vận hành biết khi nào có thể thu hồi. Thông tin nên gồm:

```text
Service account: invoice-exporter-prod
Workload sử dụng: job xuất hóa đơn cuối ngày
Chủ sở hữu: nhóm báo cáo
Môi trường: production
Nhu cầu: đọc hóa đơn tenant-42, tạo tệp xuất trong vùng lưu trữ đã chỉ định
Ngoài phạm vi: xóa hóa đơn, quản lý người dùng, thay IAM, tạo credential cho account khác
Thời điểm rà soát: theo chu kỳ và khi nghiệp vụ thay đổi
Bằng chứng kiểm chứng: trường hợp được phép và trường hợp bị từ chối
```

Đây là biểu mẫu ý tưởng, không phải cú pháp policy cho một sản phẩm cụ thể. Các giới hạn mô tả trong hồ sơ phải được triển khai bằng cơ chế thực thi phù hợp, không chỉ tồn tại trong tài liệu.

Người cấp quyền cần xem thêm những bên có thể sử dụng account và quyền quản lý chính account đó. Nếu account bị cấp quyền mới, mọi bên vốn đã có khả năng đại diện cho nó có thể nhận thêm tác động từ thay đổi này.

Vì vậy, thay đổi role của service account và thay đổi danh sách bên được impersonate account nên được xem xét cùng nhau. Mỗi thay đổi có thể trông nhỏ khi nhìn riêng, nhưng kết hợp lại có thể mở quyền production cho một nguồn không mong muốn.

## 8. Kiểm chứng quyền bằng cả trường hợp cho phép và từ chối

Một request nghiệp vụ chạy thành công chỉ chứng minh rằng đường đó đang hoạt động. Nó không chứng minh account đã bị giới hạn đúng.

Với account xuất hóa đơn, bộ tình huống kiểm chứng có thể là:

| Tình huống | Kết quả dự kiến |
| --- | --- |
| Đọc hóa đơn thuộc tenant được cấp | Cho phép |
| Đọc hóa đơn của tenant ngoài phạm vi | Từ chối |
| Tạo tệp trong vùng xuất được cấp | Cho phép |
| Ghi vào vùng lưu trữ của dịch vụ khác | Từ chối |
| Xóa hóa đơn nguồn | Từ chối |
| Gán thêm role hoặc tạo credential cho account khác | Từ chối |
| Credential staging yêu cầu nhận danh tính production | Từ chối theo chính sách trust |

Khi kiểm chứng, cần biết principal thực sự được hệ thống nhìn thấy. Một công cụ thử nghiệm có thể vô tình dùng credential cá nhân của quản trị viên hoặc một credential dự phòng thay vì service account cần kiểm tra. Kết quả thành công khi đó không có giá trị chứng minh quyền của account mục tiêu.

Có thể sử dụng công cụ phân tích policy của nền tảng, kiểm tra cấu hình và thử nghiệm trong phạm vi được phép. Mỗi cách có giới hạn: mô phỏng có thể không phản ánh mọi điều kiện runtime, còn log chỉ phản ánh các sự kiện đã xảy ra và được ghi nhận.

Không kết luận một permission không cần thiết chỉ vì không thấy nó trong log vài ngày. Một job theo quý hoặc một luồng khôi phục ít dùng có thể chưa xuất hiện trong cửa sổ quan sát. Cần đối chiếu nhu cầu nghiệp vụ, mã hoặc thiết kế đã được xác nhận và bằng chứng vận hành trước khi bỏ quyền.

Ngược lại, việc một permission từng được sử dụng cũng không chứng minh nó còn cần thiết hoặc được dùng hợp lệ. Lượt sử dụng có thể đến từ cấu hình cũ, thao tác sai hoặc một workload không nên dùng chung account.

## 9. Thay đổi và thu hồi quyền an toàn

Khi giảm quyền của một account đang phục vụ nhiều workload, cần xác định bên phụ thuộc trước. Một quy trình triển khai có thể gồm:

1. Xác nhận chủ sở hữu, workload sử dụng và tập quyền hiệu lực hiện tại.
2. Xây dựng tập quyền đích gắn với nhu cầu đã được phê duyệt.
3. Kiểm chứng ở môi trường phù hợp, gồm cả trường hợp bị từ chối.
4. Triển khai theo phạm vi kiểm soát được và theo dõi lỗi phân quyền.
5. Xác nhận quyền cũ đã thực sự bị loại bỏ tại bên thực thi.

Nếu một thao tác thiếu quyền, cần xác định hành động và tài nguyên bị từ chối rồi điều chỉnh đúng phần còn thiếu. Không tự động gán role quản trị khi gặp lỗi để khôi phục dịch vụ. Việc sửa lỗi vận hành không được biến thành cơ chế mở rộng quyền không có giới hạn.

Khi thu hồi, cần phân biệt:

- Gỡ role hoặc policy cấp quyền.
- Ngăn cấp credential mới.
- Thu hồi credential hoặc phiên đã cấp.
- Xử lý kết nối hoặc công việc đã bắt đầu dưới quyền cũ.

Một access token có thể chứa thông tin quyền tại thời điểm phát hành; một API khác có thể tra cứu chính sách hiện hành trên mỗi lần gọi. Hiệu lực của thay đổi phụ thuộc cơ chế đó, cache và thời gian đồng bộ. Không mặc định gỡ role là mọi token hoặc phiên đang tồn tại mất hiệu lực ngay lập tức.

Khi sự cố yêu cầu chặn nhanh, cần phối hợp các cơ chế mà hệ thống hỗ trợ, chẳng hạn chặn tại tài nguyên, ngăn cấp token và xử lý phiên. Đồng thời phải xác nhận rằng bên đang bị chặn không còn một đường khác để nhận lại quyền.

## 10. Rà soát đặc quyền trong suốt vòng đời

Quyền thường tích lũy qua nhiều thay đổi: service thêm chức năng mới, account vào thêm group, role được mở rộng hoặc tài nguyên chuyển sang phạm vi cha rộng hơn. Không phải lúc nào người vận hành cũng gán trực tiếp một role mới lên account.

Các sự kiện nên kích hoạt rà soát gồm:

- Nghiệp vụ hoặc nguồn dữ liệu thay đổi.
- Workload đổi môi trường, nhóm chủ sở hữu hoặc phương thức triển khai.
- Thay đổi role, thành viên group, chính sách tài nguyên hoặc trust.
- Thêm bên được phép tạo credential, impersonate hoặc gắn account vào workload.
- Workload bị ngừng sử dụng, sáp nhập hoặc thay thế.
- Phát hiện credential bị lộ hoặc hành vi sử dụng bất thường.

Account không còn workload sử dụng vẫn có thể giữ nhiều quyền và credential còn hiệu lực. Ngừng một job không tự động thu hồi quyền của account đó. Vòng đời kết thúc cần xử lý cả quyền truy cập, credential, quan hệ trust và tài nguyên phụ thuộc.

Không nên xóa account chỉ dựa trên việc không thấy hoạt động trong một thời gian ngắn. Cần xác minh các công việc ít chạy và kế hoạch khôi phục. Sau khi xác nhận không còn nhu cầu, mới thực hiện vô hiệu hóa và dọn dẹp theo quy trình có thể kiểm chứng.

## 11. Kiểm toán và phát hiện sử dụng đặc quyền

Hai loại sự kiện đều quan trọng: **thay đổi quyền** và **sử dụng quyền**. Log gọi API không đủ nếu không biết ai đã cấp role hoặc sửa trust trước đó.

Đối với thay đổi quyền, nên ghi nhận bên thực hiện, account bị tác động, nội dung thay đổi, phạm vi tài nguyên, thời điểm và tham chiếu phê duyệt khi quy trình có yêu cầu. Đối với sử dụng quyền, nên ghi principal được xác thực, hành động, tài nguyên, kết quả và mã tương quan.

Nếu có impersonation hoặc delegation, cần giữ dấu vết actor ban đầu và danh tính được đại diện theo khả năng của nền tảng. Chỉ ghi tên service account đích có thể làm mất thông tin bên đã kích hoạt thao tác.

Các tín hiệu đáng chú ý gồm account đọc dữ liệu ngoài mẫu thông thường, truy cập từ nguồn workload không dự kiến, tạo credential mới, sửa IAM hoặc được sử dụng sau khi ứng dụng đã ngừng hoạt động. Những tín hiệu này cần được đối chiếu với ngữ cảnh vận hành; không phải mọi thay đổi tần suất đều là sự cố.

Log không được chứa token, mật khẩu hoặc private key. Việc theo dõi đặc quyền cần hỗ trợ điều tra mà không tạo thêm nơi rò rỉ credential.

## 12. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu phù hợp |
| --- | --- |
| Service account là tài khoản máy nên có thể cấp quyền rộng | Phần mềm vẫn có thể bị xâm nhập; quyền cần bám sát công việc |
| Chỉ role quản trị mới là đặc quyền nguy hiểm | Đọc secret, sửa pipeline hoặc impersonate có thể tạo tác động lớn |
| Credential ngắn hạn giải quyết quyền dư thừa | Thời hạn giới hạn thời gian, không tự giới hạn hành động và tài nguyên |
| Chỉ cần xem role gán trực tiếp | Quyền có thể đến từ group, phạm vi cha, policy tài nguyên và đường ủy quyền |
| Chỉ người đọc được secret mới dùng được account | Quyền triển khai, gắn danh tính hoặc xin token cũng có thể tạo khả năng đại diện |
| Test thành công nghĩa là phân quyền đã đúng | Cần kiểm tra cả thao tác ngoài phạm vi phải bị từ chối |
| Gỡ role là mọi phiên cũ bị chặn ngay | Phải xác minh cách thực thi quyền, token, cache và phiên |
| Account không hoạt động thì không còn rủi ro | Quyền và credential có thể vẫn còn tồn tại |

Service account privilege cần được nhìn như khả năng hành động thực tế của một danh tính máy, bao gồm các đường đại diện và quyền gián tiếp. Thiết kế tốt gắn từng quyền với nhu cầu rõ ràng, bảo vệ đường thay đổi đặc quyền, kiểm chứng giới hạn tại tài nguyên và duy trì khả năng thu hồi khi nhu cầu kết thúc hoặc có sự cố.
