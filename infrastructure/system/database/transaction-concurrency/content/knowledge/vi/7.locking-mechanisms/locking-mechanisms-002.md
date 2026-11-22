# Ma trận tương thích và hàng đợi cấp khóa

Khi nhiều giao dịch cùng truy cập một dữ liệu, hệ quản trị cơ sở dữ liệu (DBMS) cần quyết định giao dịch nào được tiếp tục và giao dịch nào phải chờ. Bộ quản lý khóa (lock manager) đưa ra quyết định đó dựa trên **chế độ khóa**, **tài nguyên được khóa**, các khóa đang được cấp và những yêu cầu đang chờ.

Hai khái niệm gắn chặt với nhau:

- **Ma trận tương thích (lock compatibility matrix)** cho biết hai chế độ khóa có thể cùng tồn tại trên một tài nguyên hay không.
- **Hàng đợi cấp khóa (lock wait queue)** lưu các yêu cầu chưa thể được cấp ngay và giúp DBMS xử lý chúng khi khóa đang giữ được giải phóng.

Hiểu hai cơ chế này giúp giải thích vì sao một câu lệnh phải chờ, vì sao một giao dịch đọc vẫn có thể chặn giao dịch ghi, và vì sao đôi khi một yêu cầu khóa tương thích với khóa hiện tại vẫn phải đợi.

## 1. Khóa gồm tài nguyên và chế độ

Một yêu cầu khóa luôn gắn với một **tài nguyên (lock resource)** và một **chế độ (lock mode)**.

Tài nguyên có thể là một hàng, một khóa chỉ mục, một trang dữ liệu hoặc cả bảng. DBMS có thể dùng những mức chi tiết khác nhau tùy loại thao tác, cấu trúc lưu trữ và chiến lược khóa. Chế độ khóa mô tả quyền mà giao dịch muốn có trên tài nguyên đó.

Ví dụ, khi giao dịch đọc một hàng, DBMS có thể yêu cầu khóa chia sẻ trên hàng. Khi giao dịch sửa hàng, DBMS cần một khóa độc quyền để bảo đảm giao dịch khác không đồng thời sửa cùng tài nguyên theo cách xung đột.

Ở một thời điểm, yêu cầu khóa có thể ở một trong hai trạng thái chính:

- **Đã được cấp (granted):** giao dịch có khóa và được phép tiếp tục thao tác trong phạm vi quyền của khóa đó.
- **Đang chờ (waiting/pending):** yêu cầu chưa được cấp vì có xung đột với khóa khác hoặc vì chính sách xếp hàng của DBMS.

Ma trận tương thích trả lời câu hỏi một yêu cầu mới có thể được cấp đồng thời với các khóa đang được giữ trên cùng tài nguyên hay không. Nó không tự quyết định toàn bộ lịch chạy của giao dịch; hàng đợi và chính sách lập lịch khóa cũng tham gia vào quyết định cuối cùng.

## 2. Ma trận tương thích cơ bản: S và X

Hai chế độ thường gặp nhất là:

- **S (Shared lock – khóa chia sẻ):** dùng để đọc. Nhiều giao dịch có thể cùng giữ S trên cùng tài nguyên vì các thao tác đọc không làm thay đổi dữ liệu.
- **X (Exclusive lock – khóa độc quyền):** dùng để sửa hoặc thực hiện thao tác cần quyền truy cập độc quyền. Khi một giao dịch giữ X, giao dịch khác không thể nhận S hoặc X trên cùng tài nguyên theo ma trận cơ bản.

Ma trận tương thích cơ bản:

| Khóa đang được giữ | Yêu cầu S mới | Yêu cầu X mới |
|---|---:|---:|
| S | Có | Không |
| X | Không | Không |

Đọc ma trận theo từng dòng:

- Nếu tài nguyên đang có S, một yêu cầu S khác tương thích và có thể được cấp. Một yêu cầu X xung đột nên phải chờ.
- Nếu tài nguyên đang có X, cả yêu cầu S lẫn X đều xung đột và phải chờ.
- Nếu không có khóa xung đột, DBMS có thể cấp khóa ngay, miễn là yêu cầu cũng đáp ứng các điều kiện lập lịch và chính sách khóa khác.

Ví dụ, giao dịch T1 đọc hàng `Account(42)` và giữ S. T2 muốn cập nhật chính hàng đó nên yêu cầu X. T2 phải chờ T1 kết thúc hoặc giải phóng S. Ngược lại, nếu T2 chỉ đọc hàng đó và yêu cầu S, hai giao dịch có thể cùng đọc.

Điểm quan trọng là ma trận được áp dụng cho **cùng một tài nguyên khóa**. Một khóa S trên hàng A không tự động xung đột với khóa X trên hàng B. Tuy nhiên, khóa ở các cấp khác nhau như bảng và hàng có thể liên hệ với nhau thông qua khóa ý định trong hệ thống khóa phân cấp.

## 3. Các chế độ khóa ý định và khóa cập nhật

Trong hệ thống hỗ trợ khóa nhiều mức (multiple-granularity locking), chỉ S và X thường chưa đủ để mô tả đầy đủ cách DBMS phối hợp khóa bảng với khóa hàng. Nhiều hệ quản trị bổ sung các chế độ khóa ý định (intent locks) và khóa cập nhật (update lock).

Các tên dưới đây phổ biến trong mô hình khóa kiểu SQL Server. Chi tiết và ma trận cụ thể có thể khác giữa các DBMS; khi làm việc với một hệ quản trị cụ thể, cần đối chiếu tài liệu của hệ đó.

| Chế độ | Tên đầy đủ | Ý nghĩa |
|---|---|---|
| IS | Intent Shared | Giao dịch dự định lấy khóa S ở cấp thấp hơn, chẳng hạn khóa hàng bên trong bảng. |
| IX | Intent Exclusive | Giao dịch dự định lấy khóa X ở cấp thấp hơn. |
| SIX | Shared with Intent Exclusive | Giao dịch giữ S trên tài nguyên hiện tại và dự định lấy X ở các tài nguyên cấp thấp hơn. |
| U | Update | Giao dịch đọc tài nguyên với ý định có thể cập nhật nó sau đó; khóa này hỗ trợ chuyển sang X. |
| S | Shared | Cho phép đọc đồng thời với các khóa tương thích. |
| X | Exclusive | Cấp quyền độc quyền trên tài nguyên. |

### 3.1. Vì sao cần khóa ý định?

Giả sử T1 muốn cập nhật một hàng trong bảng `Orders`. T1 có thể giữ IX trên bảng và X trên hàng cần sửa. IX trên bảng báo cho DBMS biết rằng bên dưới bảng đang có một khóa độc quyền.

Trong khi đó, T2 muốn khóa độc quyền toàn bộ bảng. DBMS có thể kiểm tra khóa ở cấp bảng và nhận ra IX đang tồn tại. T2 không cần quét từng hàng để phát hiện xung đột. Khóa ý định giúp phối hợp các cấp khóa và tránh tình trạng một giao dịch khóa bảng trong khi giao dịch khác đang khóa các hàng bên trong bảng.

IS và IX thường được gọi là khóa ý định vì chúng thể hiện kế hoạch khóa ở cấp thấp hơn. Bản thân IS hoặc IX không có nghĩa là giao dịch đã khóa tất cả hàng trong bảng.

### 3.2. Ma trận mở rộng thường gặp

Bảng sau thể hiện quan hệ tương thích thường dùng cho sáu chế độ IS, S, U, IX, SIX và X. Dòng là khóa đang được giữ; cột là chế độ mà giao dịch mới yêu cầu. Dấu ✓ nghĩa là tương thích; dấu ✗ nghĩa là xung đột.

| Đang giữ \ Yêu cầu mới | IS | S | U | IX | SIX | X |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| IS | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| S | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| U | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| IX | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ |
| SIX | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| X | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

Ma trận này có thể đọc qua một số trường hợp tiêu biểu:

- IS tương thích với nhiều chế độ vì nó chỉ thông báo ý định khóa ở cấp thấp hơn. IS không tương thích với X trên cùng tài nguyên.
- S tương thích với IS, S và U. S không tương thích với IX, SIX hoặc X trên cùng tài nguyên.
- IX tương thích với IS và IX. Hai giao dịch có thể cùng thông báo rằng chúng sẽ khóa độc quyền các phần cấp thấp hơn, miễn là các khóa thực tế ở cấp thấp hơn không xung đột.
- SIX chỉ tương thích với IS trong ma trận này. Nó kết hợp quyền đọc trên tài nguyên hiện tại với ý định cập nhật các phần cấp thấp hơn.
- X không tương thích với bất kỳ chế độ nào khác trên cùng tài nguyên.

Không nên áp dụng ma trận mở rộng này một cách máy móc cho mọi DBMS hoặc mọi loại khóa. Một hệ thống có thể bổ sung chế độ khóa phạm vi, khóa khóa chỉ mục hoặc chế độ riêng cho một cấu trúc dữ liệu. Nguyên tắc chung vẫn là kiểm tra tương thích trên đúng loại tài nguyên và đúng mô hình khóa mà DBMS triển khai.

### 3.3. Khóa ở các cấp khác nhau

Khóa ý định giải thích vì sao hai khóa có thể không nằm trên cùng một tài nguyên nhưng vẫn được phối hợp. Ví dụ:

1. T1 giữ IX trên bảng `Orders` và X trên hàng có `order_id = 42`.
2. T2 muốn đọc toàn bộ bảng và yêu cầu S trên bảng.
3. S trên bảng không tương thích với IX đang giữ trên bảng, vì vậy T2 phải chờ.

Nếu T2 chỉ đọc một hàng cụ thể, DBMS có thể yêu cầu IS ở cấp bảng và S ở cấp hàng. IS tương thích với IX ở cấp bảng; xung đột thực tế được kiểm tra tiếp ở cấp hàng. Nếu T1 đang giữ X trên đúng hàng mà T2 muốn đọc, T2 phải chờ tại tài nguyên hàng đó. Nếu T2 đọc hàng khác, hai giao dịch có thể tiếp tục đồng thời.

Vì vậy, khi phân tích một tình huống khóa, cần xác định cả **cấp tài nguyên** lẫn **chế độ khóa**. Chỉ nhìn thấy chữ S hoặc X mà bỏ qua cấp khóa có thể dẫn đến kết luận sai về xung đột.

## 4. DBMS cấp khóa như thế nào?

Một yêu cầu khóa thường đi qua các bước khái quát sau:

1. Giao dịch yêu cầu một chế độ khóa trên một tài nguyên.
2. Lock manager tìm các khóa đã được cấp trên tài nguyên đó.
3. Lock manager kiểm tra yêu cầu mới với từng khóa đang giữ bằng ma trận tương thích.
4. Nếu yêu cầu tương thích và được phép theo chính sách xếp hàng, DBMS cấp khóa và giao dịch tiếp tục.
5. Nếu yêu cầu xung đột hoặc phải đứng sau yêu cầu đang chờ theo chính sách của DBMS, yêu cầu được đưa vào trạng thái chờ.
6. Khi một khóa được giải phóng hoặc một yêu cầu trước đó được xử lý, lock manager đánh giá lại các yêu cầu đang chờ và cấp những khóa đủ điều kiện.

Có thể hình dung trạng thái của một tài nguyên như sau:

```text
Tài nguyên: Account(42)

Khóa đã cấp:
  T1: S  [GRANTED]

Hàng đợi:
  T2: X  [WAITING]
```

T2 yêu cầu X nhưng T1 đang giữ S, nên T2 chưa được cấp khóa. Khi T1 commit hoặc rollback và S được giải phóng, lock manager có thể cấp X cho T2 nếu không còn yêu cầu hay ràng buộc nào khác ngăn cản.

Một giao dịch đang chờ khóa thường không thể tiếp tục câu lệnh cần tài nguyên đó. Các thao tác độc lập khác của hệ thống vẫn có thể chạy; việc một giao dịch chờ không có nghĩa toàn bộ DBMS bị dừng.

## 5. Hàng đợi cấp khóa và thứ tự xử lý

Hàng đợi cấp khóa lưu những yêu cầu chưa được cấp. Mỗi yêu cầu có thể gắn với giao dịch, tài nguyên, chế độ khóa và trạng thái chờ. DBMS dùng thông tin này để quyết định yêu cầu nào có thể được cấp sau khi trạng thái khóa thay đổi.

### 5.1. Một yêu cầu tương thích vẫn có thể phải chờ

Giả sử T1 đang giữ S trên tài nguyên R. T2 yêu cầu X nên phải chờ. Sau đó T3 yêu cầu S. Xét riêng ma trận tương thích với khóa đang được cấp, S của T3 tương thích với S của T1.

Tuy nhiên, nếu DBMS luôn cho yêu cầu mới vượt qua yêu cầu X cũ đang chờ, một luồng yêu cầu đọc liên tục có thể khiến T2 phải chờ rất lâu. Để hạn chế tình trạng giao dịch ghi bị bỏ đói (writer starvation), DBMS có thể giữ thứ tự ưu tiên cho yêu cầu cũ hơn và để T3 chờ phía sau T2.

```text
Tài nguyên R

Đang giữ:
  T1: S  [GRANTED]

Hàng đợi minh họa:
  T2: X  [WAITING - đến trước]
  T3: S  [WAITING - đến sau]
```

Đây là ví dụ về chính sách hàng đợi có ưu tiên theo thứ tự đến. Chính sách thực tế không giống nhau ở mọi DBMS: có hệ thống cho phép một yêu cầu tương thích vượt qua yêu cầu đang chờ trong một số điều kiện, có hệ thống ưu tiên yêu cầu cũ để bảo đảm công bằng. Vì thế, không thể suy ra quy tắc FIFO tuyệt đối chỉ từ ma trận tương thích.

### 5.2. Chặn đầu hàng đợi

Khi yêu cầu ở đầu hàng đợi chưa thể được cấp, những yêu cầu phía sau có thể bị giữ lại dù chúng tương thích với các khóa đang được cấp. Hiện tượng này thường được gọi là **head-of-line blocking**.

Chặn đầu hàng đợi là một đánh đổi giữa thông lượng và công bằng. Cho phép yêu cầu mới vượt lên có thể tăng số thao tác hoàn thành trong ngắn hạn, nhưng một yêu cầu xung đột cũ có nguy cơ chờ vô hạn. Ưu tiên yêu cầu cũ giúp hạn chế bỏ đói, nhưng có thể làm các yêu cầu tương thích phía sau phải chờ thêm.

### 5.3. Không có một hàng đợi toàn cục cho mọi khóa

Thông thường, yêu cầu được quản lý theo tài nguyên hoặc cấu trúc nội bộ của lock manager. Hai yêu cầu trên hai hàng độc lập không nhất thiết phải xếp sau nhau. Một yêu cầu khóa bảng có thể tương tác với các khóa cấp thấp hơn thông qua khóa ý định, nhưng điều đó không biến mọi yêu cầu khóa trong cơ sở dữ liệu thành một hàng đợi duy nhất.

## 6. Chuyển đổi khóa và hàng đợi chuyển đổi

Một giao dịch có thể đang giữ một chế độ khóa rồi yêu cầu chế độ mạnh hơn trên cùng tài nguyên. Việc này gọi là **chuyển đổi khóa (lock conversion hoặc lock upgrade)**.

Ví dụ, T1 đọc một hàng và giữ S. Sau khi kiểm tra giá trị, T1 muốn cập nhật hàng đó nên yêu cầu chuyển S thành X. DBMS chỉ có thể hoàn tất chuyển đổi khi X tương thích với tất cả khóa còn lại trên tài nguyên.

Nếu một giao dịch khác cũng đang giữ S và cũng muốn chuyển sang X, hai giao dịch có thể tạo ra deadlock:

```text
T1 giữ S(R)                 T2 giữ S(R)
T1 yêu cầu chuyển sang X    T2 yêu cầu chuyển sang X
T1 phải chờ T2 nhả S        T2 phải chờ T1 nhả S
```

Không giao dịch nào có thể tự giải quyết việc chờ này vì mỗi bên đang giữ khóa mà bên kia cần. DBMS có thể phát hiện chu trình chờ và chọn một giao dịch làm nạn nhân để rollback.

Một số DBMS có chế độ U (update lock) để giảm một dạng deadlock chuyển đổi thường gặp. Giao dịch lấy U khi đọc dữ liệu với ý định có thể cập nhật sau đó. U tương thích với S, nên các giao dịch khác vẫn có thể đọc; nhưng chỉ một giao dịch có thể giữ U trên cùng tài nguyên theo ma trận nêu trên. Khi giao dịch quyết định sửa dữ liệu, nó chuyển U thành X. Cách này giảm khả năng nhiều giao dịch cùng giữ S rồi đồng thời nâng cấp lên X.

Khóa U không loại bỏ mọi deadlock. Giao dịch vẫn có thể deadlock khi khóa nhiều tài nguyên theo thứ tự khác nhau hoặc khi kết hợp nhiều loại khóa.

## 7. Phân biệt blocking và deadlock

Hai hiện tượng này đều khiến giao dịch chờ, nhưng nguyên nhân khác nhau.

**Blocking (chặn):** một giao dịch phải chờ khóa do giao dịch khác đang giữ khóa xung đột. Nếu giao dịch giữ khóa hoàn tất và giải phóng khóa, giao dịch đang chờ có thể tiếp tục.

**Deadlock (bế tắc):** một nhóm giao dịch tạo thành chu trình chờ. Mỗi giao dịch giữ tài nguyên mà giao dịch khác trong chu trình cần, nên không bên nào có thể tiếp tục nếu không có sự can thiệp.

Ví dụ deadlock kinh điển:

```text
T1: giữ X(A), sau đó yêu cầu X(B)
T2: giữ X(B), sau đó yêu cầu X(A)

T1 chờ T2 giải phóng B
T2 chờ T1 giải phóng A
```

Có thể biểu diễn quan hệ chờ bằng đồ thị chờ (wait-for graph): mỗi nút là một giao dịch; cạnh `T1 → T2` nghĩa là T1 đang chờ tài nguyên do T2 giữ. Nếu đồ thị có chu trình, hệ thống có deadlock.

Hàng đợi khóa cho biết yêu cầu nào đang chờ trên tài nguyên. Đồ thị chờ giúp DBMS hoặc công cụ giám sát nhận ra chu trình deadlock. Hai cấu trúc này liên quan nhưng không phải cùng một thứ.

## 8. Khi nào khóa được giải phóng?

Thời điểm giải phóng phụ thuộc vào chế độ khóa, mức cô lập giao dịch (isolation level), loại tài nguyên và quy tắc của DBMS.

- Khóa X dùng để bảo vệ thay đổi thường được giữ đến khi giao dịch commit hoặc rollback.
- Khóa S có thể được giải phóng sớm hơn hoặc giữ đến cuối giao dịch tùy mức cô lập và cơ chế của DBMS.
- Khóa dùng để bảo vệ phạm vi hoặc điều kiện truy vấn có thể có thời hạn và quy tắc riêng để ngăn các thay đổi gây vi phạm mức cô lập.

Khi khóa được giải phóng, lock manager xem xét các yêu cầu đang chờ. Một yêu cầu được cấp có thể đánh thức giao dịch tương ứng để tiếp tục câu lệnh.

Nếu giao dịch giữ khóa quá lâu, các giao dịch khác có thể bị chặn lâu theo. Những nguyên nhân thường gặp gồm giao dịch mở quá lâu, ứng dụng giữ transaction trong lúc chờ thao tác bên ngoài, truy vấn cập nhật nhiều hàng, hoặc câu lệnh đọc cần mức khóa mạnh do mức cô lập đang dùng.

DBMS thường có cơ chế timeout hoặc hủy yêu cầu chờ. Timeout giúp giới hạn thời gian chờ, nhưng không tự sửa nguyên nhân gây tranh chấp. Deadlock thường được xử lý bằng cơ chế phát hiện và chọn giao dịch để rollback; đây là cơ chế khác với timeout thông thường.

## 9. Khóa nhiều hàng và lock escalation

Khi một giao dịch khóa nhiều hàng, DBMS phải quản lý nhiều mục khóa. Việc này tiêu tốn bộ nhớ và công sức quản lý. Một số DBMS có thể thực hiện **lock escalation**: thay nhiều khóa chi tiết bằng một khóa ở cấp cao hơn, chẳng hạn chuyển từ nhiều khóa hàng sang khóa bảng.

Escalation có thể giảm chi phí quản lý khóa, nhưng khóa ở cấp cao hơn thường làm giảm khả năng các giao dịch khác truy cập đồng thời vào những hàng độc lập trong bảng. Ví dụ, T1 chỉ cập nhật một tập hàng nhưng sau khi escalation giữ X ở cấp bảng; T2 muốn đọc một hàng khác trong bảng có thể phải chờ.

Không phải DBMS nào cũng escalation theo cùng cách, và ngưỡng hoặc điều kiện escalation có thể phụ thuộc cấu hình, áp lực bộ nhớ và loại khóa. Khi điều tra blocking, cần xem tài nguyên thực tế đang bị khóa thay vì mặc định rằng câu lệnh chỉ khóa đúng hàng mà nó nhắc đến.

## 10. Ví dụ theo dõi một hàng đợi khóa

Giả sử có hai giao dịch thao tác trên `Inventory(item_id = 7)`.

```sql
-- Giao dịch T1
BEGIN;
SELECT quantity
FROM Inventory
WHERE item_id = 7;
-- Trong mô hình khóa đang xét, T1 giữ S trên hàng.
```

Trong lúc T1 chưa kết thúc, T2 thực hiện cập nhật:

```sql
-- Giao dịch T2
BEGIN;
UPDATE Inventory
SET quantity = quantity - 1
WHERE item_id = 7;
-- T2 cần quyền ghi, nên yêu cầu X trên hàng.
-- X xung đột với S của T1; T2 phải chờ.
```

Trạng thái khái quát:

| Giao dịch | Tài nguyên | Chế độ | Trạng thái |
|---|---|---|---|
| T1 | Inventory(7) | S | Đã cấp |
| T2 | Inventory(7) | X | Đang chờ |

Khi T1 hoàn tất:

```sql
-- Giao dịch T1
COMMIT;
```

DBMS giải phóng khóa S của T1. Nếu không còn yêu cầu hoặc điều kiện xung đột khác, X của T2 được cấp và câu lệnh UPDATE tiếp tục. Sau khi T2 hoàn tất, DBMS giải phóng khóa X:

```sql
-- Giao dịch T2
COMMIT;
```

Ví dụ này minh họa nguyên tắc chung. Cú pháp SQL, thời điểm lấy khóa đọc và thời điểm giải phóng khóa có thể khác theo DBMS và isolation level. Một số hệ thống dùng MVCC để phục vụ nhiều thao tác đọc bằng phiên bản dữ liệu; trong các trường hợp đó, một truy vấn đọc thông thường có thể không lấy S theo cách minh họa. Các thao tác ghi vẫn phải phối hợp để tránh cập nhật xung đột.

## 11. Cách đọc một tình huống blocking trong thực tế

Khi một câu lệnh bị chậm do chờ khóa, hãy lần lượt xác định:

1. **Giao dịch nào đang chờ?** Tìm session hoặc transaction có trạng thái chờ khóa.
2. **Giao dịch nào đang chặn?** Xác định session giữ khóa xung đột và thời điểm transaction bắt đầu.
3. **Tài nguyên nào bị tranh chấp?** Đó là hàng, khóa chỉ mục, trang, bảng hay một phạm vi dữ liệu?
4. **Chế độ nào đang được giữ và được yêu cầu?** Đối chiếu hai chế độ với ma trận tương thích của DBMS.
5. **Vì sao khóa chưa được giải phóng?** Kiểm tra transaction mở lâu, câu lệnh chạy lâu, ứng dụng chưa commit/rollback hoặc truy vấn đang chờ một thao tác khác.
6. **Có chu trình chờ không?** Nếu có, đây có thể là deadlock; nếu không, nhiều khả năng là blocking thông thường.

Khi xử lý, thường nên rút ngắn thời gian sống của transaction, cập nhật theo thứ tự tài nguyên nhất quán, tạo chỉ mục phù hợp để giảm số hàng cần kiểm tra và chỉ giữ transaction trong phạm vi công việc cần thiết. Việc thay đổi isolation level hoặc cơ chế khóa cần dựa trên yêu cầu nhất quán dữ liệu của ứng dụng.

Không nên coi việc bỏ qua khóa đọc là cách sửa mặc định. Chẳng hạn, một tùy chọn đọc dữ liệu chưa commit có thể tránh chờ trong một số tình huống nhưng đổi lại ứng dụng có thể đọc giá trị chưa được xác nhận, dữ liệu không nhất quán hoặc kết quả không lặp lại được. Cần chọn giải pháp theo ngữ nghĩa dữ liệu mà ứng dụng yêu cầu.

## 12. Những điểm cần ghi nhớ

- Tương thích được quyết định bởi **chế độ khóa trên cùng tài nguyên**; cấp khóa cũng chịu ảnh hưởng của thứ tự hàng đợi và chính sách DBMS.
- S thường cho phép nhiều giao dịch đọc đồng thời; X cần quyền độc quyền và xung đột với các chế độ khác trên cùng tài nguyên.
- IS và IX thông báo ý định khóa ở cấp thấp hơn, giúp phối hợp khóa bảng, trang và hàng.
- Hàng đợi lưu các yêu cầu chưa được cấp. Chính sách ưu tiên có thể khiến yêu cầu mới tương thích với khóa đang giữ vẫn phải chờ phía sau yêu cầu cũ.
- Chuyển S sang X có thể gây deadlock nếu nhiều giao dịch cùng nâng cấp; U là một cơ chế giảm một số trường hợp như vậy.
- Blocking có thể kết thúc khi khóa được giải phóng. Deadlock có chu trình chờ và cần cơ chế phát hiện, phá vỡ chu trình.
- Ma trận cụ thể, chính sách hàng đợi, thời điểm giải phóng và lock escalation phụ thuộc DBMS. Khi chẩn đoán, hãy dùng đúng tài liệu và công cụ giám sát của hệ quản trị đang vận hành.
