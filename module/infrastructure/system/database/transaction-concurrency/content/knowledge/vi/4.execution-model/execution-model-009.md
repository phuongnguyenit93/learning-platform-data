# Phân biệt khả tuần tự với khả tuần tự nghiêm ngặt (strict serializability)

Khi nhiều giao dịch cùng chạy, cơ sở dữ liệu cần đưa ra một kết quả có thể hiểu được dù các thao tác đọc và ghi xen kẽ nhau. **Khả tuần tự (serializability)** và **khả tuần tự nghiêm ngặt (strict serializability)** đều mô tả tính đúng đắn của *lịch thực thi giao dịch* (transaction history). Chúng khác nhau ở một điều then chốt: **thứ tự thời gian thực mà các client quan sát được**.

- **Serializability** yêu cầu hiệu ứng của các giao dịch tương đương một thứ tự thực thi tuần tự hợp lệ. Thứ tự tương đương này **không nhất thiết phải giữ** thứ tự các giao dịch đã kết thúc trước khi giao dịch khác bắt đầu.
- **Strict serializability** yêu cầu serializability **và** tôn trọng thứ tự thời gian thực: nếu một giao dịch hoàn tất trước khi giao dịch khác bắt đầu, thứ tự tuần tự tương đương phải đặt giao dịch đã hoàn tất ở trước.

Nói cách khác, serializability trả lời **“Có thể giải thích kết quả như thể các giao dịch chạy lần lượt hay không?”**; strict serializability hỏi thêm **“Cách giải thích đó có giữ được các quan hệ trước–sau mà client thực sự quan sát không?”**

Đây là sự phân biệt quan trọng trong hệ cơ sở dữ liệu phân tán, dịch vụ có nhiều replica và luồng nghiệp vụ đòi hỏi “đã nhận xác nhận thành công thì yêu cầu mới phải thấy kết quả”.

## 1. Trước hết: lịch giao dịch là gì?

Giả sử có hai giao dịch `T1` và `T2` truy cập cùng dữ liệu. Một **lịch thực thi** (schedule/history) mô tả các sự kiện bắt đầu, đọc, ghi, commit, phản hồi và thời điểm các giao dịch xen kẽ.

Ví dụ, với giá trị ban đầu `x = 0`:

```text
Thời gian   Giao dịch T1                 Giao dịch T2
----------------------------------------------------------------
t1          BEGIN
t2          READ(x) -> 0
t3                                        BEGIN
t4                                        READ(x) -> 0
t5          WRITE(x, 1)
t6          COMMIT thành công
t7                                        COMMIT thành công
```

Hai giao dịch đã **chồng lấn về thời gian** (overlap): `T2` bắt đầu trước khi `T1` hoàn tất. Một lịch có xen kẽ thao tác chưa chắc sai. Điều cần đánh giá là lịch đó có tương đương một lịch tuần tự và đáp ứng những cam kết bổ sung hay không.

**Lịch tuần tự (serial schedule)** là lịch trong đó toàn bộ thao tác của một giao dịch kết thúc trước khi giao dịch kế tiếp thực hiện thao tác của nó:

```text
T1: [BEGIN --- đọc/ghi --- COMMIT]
T2:                              [BEGIN --- đọc/ghi --- COMMIT]
```

Ngược lại, lịch thực tế có thể đồng thời nhưng vẫn **serializable** vì kết quả tương đương một lịch tuần tự. Không cần DBMS bắt các giao dịch chạy từng cái một để đạt tính khả tuần tự.

### Những gì phải quan sát trong history

Để hiểu chính xác strict serializability, cần phân biệt hai loại mốc:

| Mốc | Ý nghĩa |
|---|---|
| **Invocation / bắt đầu** | Client gọi giao dịch hoặc yêu cầu bắt đầu thao tác giao dịch ở API đang xét. |
| **Response / hoàn tất** | Client nhận được phản hồi xác định giao dịch đã kết thúc thành công hoặc thất bại. |
| **READ / WRITE** | Các thao tác trên dữ liệu trong giao dịch. |
| **COMMIT / ABORT** | Kết quả xác nhận hoặc hủy giao dịch. |

Trong một hệ phân tán, **thời điểm một server nội bộ xử lý xong** và **thời điểm client nhận phản hồi** có thể khác nhau. Khi nói thứ tự thời gian thực của các thao tác ở API, tiêu chí quan trọng là thời điểm thao tác trước đã **hoàn tất với client** trước khi thao tác sau **được gọi**.

Để đơn giản, các ví dụ bên dưới tập trung vào giao dịch đã commit thành công, trên cùng một cơ sở dữ liệu logic. Giao dịch bị hủy và yêu cầu chưa có phản hồi cần được xử lý theo mô hình history đầy đủ của hệ thống.

## 2. Serializability: kết quả tương đương một thứ tự tuần tự

Một history là **serializable** khi tồn tại ít nhất một thứ tự tuần tự của các giao dịch sao cho các quan sát đọc và hiệu ứng dữ liệu tương đương với history thực tế theo mô hình tương đương được sử dụng.

Ví dụ có hai giao dịch:

```text
T1: chuyển 30 từ A sang B
    A = A - 30
    B = B + 30

T2: đọc cả A và B để lập báo cáo
```

Ban đầu `A = 100`, `B = 100`. Nếu `T2` thực sự đọc cả hai giá trị trong **một transaction serializable**, lịch hợp lệ có thể tương đương:

- `T2 → T1`: `T2` thấy `(A, B) = (100, 100)`.
- `T1 → T2`: `T2` thấy `(A, B) = (70, 130)`.

Dưới giả định cả hai thay đổi chuyển tiền và hai phép đọc đều thuộc các giao dịch đã mô tả, một kết quả `(70, 100)` không thể được giải thích bằng một trong hai thứ tự tuần tự này, nên là dấu hiệu thiếu tính nhất quán giao dịch. Nếu báo cáo đọc hai giá trị trong **hai transaction riêng**, bài toán lại khác: một giao dịch serializable cho từng phép đọc không tự biến hai lần đọc rời rạc thành một snapshot nguyên tử.

### 2.1. Chú ý: “tương đương” không có nghĩa phải cùng thứ tự bắt đầu

Có thể có nhiều thứ tự tuần tự tương đương. Khi hai giao dịch không tương tác hoặc chạy chồng lấn, DBMS có quyền chọn thứ tự giải thích phù hợp miễn không trái với các phụ thuộc phải giữ theo mô hình serializability.

Serializability thông thường **không bắt buộc** một giao dịch đã kết thúc trước khi giao dịch khác bắt đầu phải đứng trước giao dịch đó trong thứ tự tương đương. Đây chính là khoảng cách giữa serializability và strict serializability.

### 2.2. Conflict serializability và đồ thị phụ thuộc

Một cách kiểm tra quen thuộc trong lý thuyết database là **conflict serializability**. Với các thao tác xung đột (đọc–ghi, ghi–đọc, ghi–ghi trên cùng mục dữ liệu), dựng cạnh trong **precedence graph**:

```text
T1 --xung đột bắt buộc trước--> T2
```

Nếu đồ thị **không có chu trình**, lịch được xem là conflict-serializable theo mô hình giao dịch/đọc-ghi thích hợp. Nếu có chu trình, lịch không conflict-serializable. Đây là công cụ hữu ích để giải thích phụ thuộc, nhưng không phải mọi khái niệm tương đương lịch đều đồng nhất với conflict serializability; khái niệm view serializability rộng hơn trong lý thuyết.

Quan trọng hơn, **đồ thị xung đột dựa trên thao tác dữ liệu có thể bỏ sót yêu cầu thời gian thực**. Strict serializability còn đòi hỏi quan hệ trước–sau giữa các giao dịch không chồng lấn.

## 3. Strict serializability: thêm ràng buộc thời gian thực

Strict serializability là một bảo đảm mạnh hơn. Có thể phát biểu:

Một history giao dịch là **strictly serializable** nếu có một thứ tự giao dịch tuần tự tương đương với history ấy và thứ tự này còn thỏa mãn:

> Nếu phản hồi hoàn tất của `T1` xảy ra trước khi lời gọi bắt đầu `T2`, thì `T1` phải đứng trước `T2` trong thứ tự tuần tự.

Ký hiệu `T1 <rt T2` để chỉ quan hệ “`T1` kết thúc trước khi `T2` bắt đầu” (real-time order). Nếu `S` là thứ tự tuần tự tương đương, strict serializability yêu cầu:

```text
T1 <rt T2   =>   T1 đứng trước T2 trong S
```

Đây là dạng **linearizability áp dụng cho giao dịch nguyên tử**: mỗi giao dịch có thể được hình dung như có một điểm hiệu lực logic (linearization point) nằm trong khoảng từ lúc được gọi đến lúc trả kết quả. DBMS vẫn có thể xử lý nhiều giao dịch đồng thời; điểm hiệu lực là cách giải thích trừu tượng về hành vi quan sát được, không nhất thiết là một lệnh máy hoặc thời điểm khóa cụ thể.

### 3.1. Lịch serializable nhưng không strictly serializable

Giá trị ban đầu của `x` là `0`. Xét history:

```text
Thời gian         T1: ghi x = 1                T2: đọc x
----------------------------------------------------------------
t1                BEGIN
t2                WRITE(x, 1)
t3                COMMIT thành công
t4                Client nhận response OK
t5                                             BEGIN
t6                                             READ(x) -> 0
t7                                             COMMIT thành công
t8                                             Client nhận response OK
```

Ở đây `T1` đã **hoàn tất** trước khi `T2` bắt đầu. Không có giao dịch nào khác ghi lại `x = 0` trong khoảng này.

- Theo **serializability đơn thuần**, giá trị `READ(x) = 0` có thể được giải thích bằng thứ tự tuần tự `T2 → T1`. `T2` đọc giá trị ban đầu; sau đó `T1` ghi `1`.
- Theo **strict serializability**, thứ tự `T2 → T1` bị cấm vì thời gian thực yêu cầu `T1 → T2`. Nếu `T1` đứng trước `T2`, lần đọc của `T2` phải trả `1`. Vì vậy history **không strictly serializable**.

Đây là phản ví dụ điển hình, tách bạch hai tiêu chí bằng một giao dịch ghi và một giao dịch đọc.

Tình huống có thể được hình dung khi hệ thống cho phép giao dịch đọc từ một snapshot hoặc replica cũ dù transaction ghi đã trả kết quả thành công. Tuy nhiên, **không được mặc định một DBMS cụ thể với cấu hình `SERIALIZABLE` sẽ tạo ra lịch này**; nhiều triển khai trên primary có những bảo đảm mạnh hơn. Mục đích của lịch là làm rõ **định nghĩa logic** của hai mức bảo đảm.

### 3.2. Khi giao dịch chồng lấn, strict serializability vẫn cho phép linh hoạt

Xét một lịch khác:

```text
Thời gian         T1                           T2
---------------------------------------------------------------
t1                BEGIN
t2                                             BEGIN
t3                WRITE(x, 1)
t4                COMMIT; trả OK
t5                                             READ(x) -> 0
t6                                             COMMIT; trả OK
```

`T2` **đã bắt đầu trước khi `T1` hoàn tất**, do đó hai giao dịch chồng lấn. Quan hệ thời gian thực giữa hai **giao dịch nguyên khối** không ép buộc `T1` đứng trước `T2`. Về mặt định nghĩa, thứ tự tuần tự `T2 → T1` vẫn có thể hợp lệ nếu không có phụ thuộc hoặc lời hứa API khác khiến nó không hợp lệ.

Điểm tinh tế là: mặc dù **lệnh đọc** của `T2` diễn ra sau commit của `T1`, **transaction `T2` bắt đầu trước khi `T1` kết thúc**. Strict serializability xử lý thứ tự của toàn bộ giao dịch, không buộc mọi câu `SELECT` nội bộ thấy giá trị mới nhất tại thời điểm câu SQL ấy chạy.

Nếu thay history sao cho `T2` chỉ được **bắt đầu sau** lúc client của `T1` nhận phản hồi OK, yêu cầu thời gian thực mới ép `T1 → T2`.

## 4. So sánh trực tiếp hai mức bảo đảm

| Tiêu chí | Serializability | Strict serializability |
|---|---|---|
| Tồn tại lịch giao dịch tuần tự tương đương | **Bắt buộc** | **Bắt buộc** |
| Giữ quan hệ kết thúc–bắt đầu của hai giao dịch không chồng lấn | **Không bắt buộc** | **Bắt buộc** |
| Giao dịch bắt đầu sau một lần ghi đã xác nhận được phép đọc giá trị cũ, khi không có ghi khác | Có thể hợp lệ về **định nghĩa serializability** nếu thứ tự tương đương đặt đọc trước ghi | **Không hợp lệ** |
| Cho phép các giao dịch chạy vật lý đồng thời | Có | Có |
| Chấp nhận mọi anomaly của snapshot isolation | Không | Không |
| Tự bảo đảm quy tắc nghiệp vụ được lập trình đúng | Không | Không |
| Cần giải quyết những xung đột không thể xếp thành lịch hợp lệ | Có | Có |
| Mối quan hệ sức mạnh | Yếu hơn strict serializability | Mạnh hơn serializability |

Quan hệ tập hợp có thể biểu diễn:

```text
Các history strict serializable
             ⊂
Các history serializable

=> Strict serializable  => Serializable
=> Serializable         =/=> Strict serializable
```

Dấu bao hàm ở đây mô tả **tập lịch có thể chấp nhận**, chứ không mô tả tốc độ, hiệu năng hay việc một DBMS bắt buộc phải chạy từng transaction một.

## 5. Phân biệt với các khái niệm dễ nhầm

### 5.1. “Strict schedule” không phải “strict serializability”

Trong lý thuyết đồng thời của database, một **strict schedule** thường là lịch không cho giao dịch khác đọc hoặc ghi đè mục dữ liệu đã bị một giao dịch **chưa hoàn tất** ghi. Mục tiêu chủ yếu là tránh dirty read, dirty write và hỗ trợ khả năng phục hồi không gây cascading abort.

Quy tắc đó **không tự chứng minh serializability**.

Ví dụ write skew sau có thể không đọc dữ liệu chưa commit nhưng vẫn không serializable:

```text
Ban đầu: Doctor A.on_call = true
         Doctor B.on_call = true
Quy tắc: phải luôn có ít nhất một bác sĩ trực.

T1: READ(A, B) -> cả hai đang trực
T2: READ(A, B) -> cả hai đang trực
T1: WRITE(A.on_call = false)
T2: WRITE(B.on_call = false)
T1: COMMIT
T2: COMMIT
```

Hai giao dịch chỉ ghi **hai hàng khác nhau**, không đọc bản ghi chưa commit của nhau, nhưng nếu cả hai commit thì quy tắc bị phá vỡ. Trong mọi lịch tuần tự tuân thủ phép kiểm tra “chỉ nghỉ nếu còn người khác trực”, giao dịch chạy thứ hai sẽ thấy chỉ còn một bác sĩ trực và không được cho người cuối cùng nghỉ. Vì thế lịch có cả hai commit không thể tương đương lịch tuần tự hợp lệ của chính logic này.

**Strict** trong “strict schedule” nói về hạn chế truy cập thay đổi chưa commit. **Strict** trong “strict serializability” nói về **serializability kết hợp thứ tự thời gian thực**.

### 5.2. Strict two-phase locking (strict 2PL) không phải tên gọi khác của strict serializability

**Two-phase locking (2PL)** là họ kỹ thuật khóa với giai đoạn lấy thêm khóa rồi chuyển sang giai đoạn nhả khóa. **Strict 2PL** bổ sung quy tắc giữ các khóa ghi độc quyền đến khi transaction kết thúc, giúp tránh đọc/ghi dữ liệu chưa commit và thuận lợi cho phục hồi.

Khi 2PL được áp dụng đầy đủ lên các xung đột cần bảo vệ, nó là một cách thực thi serializability. Nhưng:

- **Strict 2PL là thuật toán/cơ chế khóa**; **strict serializability là thuộc tính quan sát được của lịch giao dịch**.
- Hệ thống có thể đạt strict serializability bằng các cơ chế khác như xác nhận giao dịch theo thứ tự, MVCC kết hợp kiểm tra xung đột và phối hợp trên các node.
- Nếu dịch vụ cho đọc từ cache/replica cũ ngoài cùng phạm vi giao dịch mạnh, chỉ nói “primary dùng strict 2PL” chưa đủ để hứa strict serializability cho **toàn bộ API**.
- Chữ “strict” của strict 2PL xuất phát từ cách giữ khóa ghi, không phải một định nghĩa trực tiếp về thời gian thực giữa lời gọi và phản hồi API.

Trong kiến trúc tập trung với khóa đầy đủ và commit chỉ trả thành công khi trạng thái mới đã có hiệu lực, một triển khai 2PL có thể đáp ứng thứ tự thời gian thực. Điều đó là tính chất cần chứng minh từ triển khai, không phải vì hai thuật ngữ có cùng chữ “strict”.

### 5.3. Linearizability của từng khóa khác với strict serializability của transaction nhiều hàng

**Linearizability** thông thường được mô tả cho các thao tác trên một đối tượng logic, ví dụ một register `x` với `read(x)` và `write(x)`. Mỗi thao tác phải có thể được đặt tại một điểm giữa lúc gọi và lúc trả lời, đồng thời giữ thứ tự thời gian thực.

Strict serializability áp dụng cách nhìn tương tự cho **cả một giao dịch nguyên tử**, có thể chứa nhiều phép đọc/ghi trên nhiều hàng hoặc bảng.

Một hệ thống có thể cung cấp đọc/ghi **linearizable cho từng key** mà chưa chắc có **transaction nguyên tử và serializable trên nhiều key**. Chẳng hạn, chuyển tiền cập nhật A rồi B thành hai thao tác key riêng sẽ có khoảng thời gian người đọc nhìn thấy A đã trừ nhưng B chưa cộng. Mỗi thao tác key có thể hoàn toàn linearizable, song toàn bộ chuyển tiền chưa phải một giao dịch strictly serializable.

### 5.4. Snapshot isolation và REPEATABLE READ không mặc nhiên serializable

**Snapshot isolation (SI)** cho một giao dịch đọc từ một snapshot ổn định và thường ngăn các trường hợp ghi xung đột trực tiếp giữa các giao dịch đồng thời. Nhưng SI có thể cho phép **write skew**, khiến kết quả không serializable.

Vì vậy:

```text
Snapshot nhất quán
   không tự suy ra Serializable
Serializable
   không tự suy ra Strict Serializable
Strict Serializable
   bao hàm Serializable và giữ real-time order
```

Tên isolation level trong SQL và cơ chế thực tế cũng phụ thuộc sản phẩm. Ví dụ `REPEATABLE READ`, `SERIALIZABLE` và các tùy chọn đọc snapshot ở các DBMS khác nhau không được đồng nhất chỉ theo tên. Đặc biệt, tính nhất quán khi đọc từ secondary/replica có thể là hợp đồng riêng so với các transaction tại primary.

### 5.5. Session consistency và causal consistency cũng không đồng nghĩa strict serializability

**Read-your-writes** giúp một client nhìn thấy những thay đổi do chính mình đã ghi. **Monotonic reads** tránh việc một client thấy dữ liệu “đi lùi” giữa các lần đọc theo chính sách session. **Causal consistency** bảo vệ một số quan hệ phụ thuộc nhân quả.

Những tính chất đó có giá trị, nhưng không tự khẳng định:

- Mọi giao dịch đều serializable trên toàn bộ tập dữ liệu.
- Giao dịch của **client B** bắt đầu sau khi giao dịch của **client A** hoàn tất sẽ quan sát thứ tự tương ứng.
- Các thao tác nhiều hàng được nhìn như một đơn vị transaction nguyên tử.

Strict serializability là một bảo đảm **toàn cục trên lịch giao dịch trong phạm vi dữ liệu được cam kết**, không chỉ là thỏa thuận cho từng session độc lập.

## 6. Ví dụ nghiệp vụ: một ghi nhận đã thành công rồi yêu cầu khác bắt đầu

Giả sử API quản lý cấu hình có cờ `feature_enabled`. Client A bật tính năng rồi nhận kết quả “thành công”; sau đó Client B mới truy vấn tình trạng của tính năng.

```text
Client A                        Dịch vụ                         Client B
   |                                |                                |
   |-- set(true) ------------------>|                                |
   |<----------------------- SUCCESS|                                |
   |                                |<------------------- get() -----|
   |                                |------ false ------------------>|
```

Giả sử không có ai ghi `false` trở lại:

- Một hệ thống **chỉ hứa serializability** vẫn có thể cho lịch trên nếu các giao dịch tương đương thứ tự “đọc false trước, ghi true sau”. Tuy nhiên nó **không phù hợp kỳ vọng về thứ tự thời gian thực** mà hai client vừa tạo ra.
- Một hệ thống **hứa strict serializability cho cả đường ghi và đường đọc** không được trả `false` trong yêu cầu đọc bắt đầu sau phản hồi thành công của lần ghi. Nó phải trả giá trị mới, hoặc không hoàn tất giao dịch đọc thành công trong thời điểm chưa đáp ứng được cam kết, tùy API và chính sách lỗi.

Cần xem **SUCCESS có nghĩa gì**. Nếu A chỉ nhận “đã xếp hàng xử lý” (`202 Accepted`), hoặc phản hồi xác nhận một bước trung gian chứ chưa phải commit giao dịch, thì chưa có cơ sở để đòi B nhìn thấy thay đổi đã commit. Phải định nghĩa rõ ràng thời điểm nào là **commit được xác nhận**.

### 6.1. Đọc qua replica bất đồng bộ

Đây là tình huống trực quan:

```text
       T1 ghi trên Primary                  T2 đọc trên Replica
               |                                   |
       COMMIT thành công                           |
               |                                   |
       Trả SUCCESS cho A                          |
               |                                   |
               +------ replication đang trễ ------+
                                                   |
                                       B bắt đầu transaction đọc
                                       -> nhìn thấy dữ liệu cũ
```

Một dịch vụ có thể cung cấp giao dịch serializable ở primary nhưng cho phép **stale reads** tại replica qua một endpoint riêng. Nếu người dùng nhầm rằng endpoint đọc cũ cũng có strict serializability, họ sẽ thấy vi phạm kỳ vọng “ghi thành công rồi đọc phải thấy”.

Cần xác định **phạm vi bảo đảm**: strict serializability được hứa cho cả read/write transactions trên mọi endpoint, chỉ cho primary, hay chỉ khi chọn một chế độ đọc nhất quán mạnh? Không thể gộp mọi đường đọc có chất lượng khác nhau vào cùng một lời hứa.

### 6.2. Đơn hàng và trạng thái thanh toán

Giả sử giao dịch `Tpay` chuyển đơn sang `PAID` và commit thành công, sau đó mới có `Tship` đọc trạng thái để quyết định phát hàng.

Nếu `Tship` bắt đầu **sau khi** lời xác nhận commit của `Tpay` đến client, strict serializability đặt `Tpay` trước `Tship`. Vì vậy `Tship` không thể dựa trên snapshot cũ `UNPAID` trong một lịch strictly serializable của cùng dữ liệu logic khi không có ghi xen vào.

Nếu chỉ dùng serializability, việc đọc snapshot cũ có thể vẫn được giải thích bằng một thứ tự tuần tự khác, dù thứ tự đó trái với thời gian thực. Điều này ảnh hưởng đến ứng dụng đòi hỏi tính mới của trạng thái sau khi đã nhận xác nhận thanh toán.

Ngay cả strict serializability **không tự bảo đảm** giao dịch với cổng thanh toán bên ngoài và ghi database là một đơn vị nguyên tử, không ngăn request trùng và không thay thế quy tắc phân quyền. Những yêu cầu đó cần các cơ chế nghiệp vụ riêng.

## 7. Cách nhận diện real-time order trong history

Để kiểm tra một history, trước tiên dựng **quan hệ giữa các giao dịch không chồng lấn**.

Ví dụ:

```text
Timeline -------------------------------------------------------->

T1: [begin ------ commit, response]
T2:                [begin ------ commit, response]
T3:                                               [begin -- response]
```

Trong sơ đồ trên:

- `T1` và `T2` **chồng lấn**: `T2` bắt đầu trước khi `T1` kết thúc. Real-time order không ép thứ tự giữa chúng chỉ dựa trên khoảng thời gian.
- `T1` kết thúc trước khi `T3` bắt đầu: bắt buộc `T1 <rt T3`.
- `T2` kết thúc trước khi `T3` bắt đầu: bắt buộc `T2 <rt T3`.

Bất kỳ thứ tự tuần tự nào dùng để chứng minh strict serializability đều phải đặt `T3` sau cả `T1` và `T2`. Tùy các phụ thuộc đọc/ghi, quan hệ giữa `T1` và `T2` có thể là một trong hai hướng.

Một cách nhìn bằng đồ thị:

```text
Các cạnh do phụ thuộc dữ liệu:
  T1 -> T2 ... (tùy read/write)

Các cạnh do thời gian thực:
  T1 -> T3
  T2 -> T3

Thứ tự tuần tự hợp lệ phải thỏa tất cả
những ràng buộc tương ứng.
```

Với mô hình giao dịch nhiều phiên bản hoặc history phức tạp, việc kiểm tra đúng đắn không chỉ là cộng thêm cạnh vào một đồ thị conflict đơn giản. Phải xét các giá trị đã đọc, quan hệ phiên bản và những ràng buộc tương đương lịch được dùng. Tuy nhiên, **quan hệ kết thúc–bắt đầu** là điểm khác biệt không thể bỏ qua.

### 7.1. Không có chồng lấn không đồng nghĩa server phải xếp hàng vật lý

Strict serializability không yêu cầu server thực thi transaction theo một hàng đợi duy nhất. DBMS vẫn có thể:

- Cho các transaction trên những dữ liệu độc lập chạy song song.
- Dùng MVCC để tránh khóa nhiều truy vấn đọc thông thường.
- Sắp xếp hoặc xác nhận giao dịch theo các ràng buộc xung đột.
- Dùng giao thức đồng thuận, timestamp có kiểm soát hoặc cơ chế phối hợp khác tùy kiến trúc.

Điều cần thỏa là **lịch sử quan sát được bên ngoài**, không phải mọi bước thực thi nội bộ phải tuần tự.

## 8. Không nhầm thứ tự thời gian thực với timestamp lưu trong dữ liệu

Strict serializability dựa trên quan hệ thật **“phản hồi của T1 xảy ra trước lời gọi T2”**. Đây là quan hệ nguyên nhân quan sát được, không đơn giản là so sánh hai trường `created_at`.

Ví dụ, hai client có đồng hồ lệch nhau. Client B gắn timestamp nhỏ hơn dù bắt đầu transaction sau khi nhận tín hiệu hoàn tất từ client A. Đồng hồ hệ thống có thể đổi giờ hoặc có sai số. Vì vậy:

- Chỉ so sánh `NOW()` hoặc timestamp gắn ở client chưa đủ để chứng minh real-time order.
- Hệ phân tán có thể dùng đồng hồ đồng bộ và chờ an toàn, hoặc dùng giao thức phối hợp không phụ thuộc đồng hồ tuyệt đối, để giữ thứ tự thực tế.
- Quan hệ nhân quả rõ ràng nhất trong kiểm thử là **đợi A nhận SUCCESS, sau đó mới gọi B**. Không cần đồng bộ đồng hồ của hai máy để biết thứ tự này.

Cũng cần phân biệt thứ tự **commit nội bộ**, thứ tự **nhận thông điệp**, thứ tự **đồng bộ replica**, và thứ tự **phản hồi cho client**. Chúng không phải lúc nào cũng trùng nhau.

## 9. Kiểm chứng bằng hai client và transaction rõ ràng

Một phép thử cơ bản là dùng hai connection hoặc hai client độc lập. Dưới đây là **kịch bản logic** có thể chuyển thành SQL theo DBMS đang sử dụng; chưa phải phép chứng minh đầy đủ cho mọi lịch.

### 9.1. Chuẩn bị dữ liệu

```sql
CREATE TABLE consistency_probe (
    id BIGINT PRIMARY KEY,
    value_num INTEGER NOT NULL
);

INSERT INTO consistency_probe (id, value_num)
VALUES (1, 0);
```

Chỉ thực hiện trên bảng thử nghiệm riêng, sau khi đã biết các lệnh setup đã được commit.

### 9.2. Kiểm tra thứ tự non-overlap

**Client A:** bắt đầu transaction ghi và chờ xác nhận commit thật sự.

```sql
BEGIN;

UPDATE consistency_probe
SET value_num = 1
WHERE id = 1;

COMMIT;
-- Chờ client nhận kết quả COMMIT thành công.
```

**Client B:** *chỉ bắt đầu transaction đọc sau* khi client A đã nhận thành công:

```sql
BEGIN;

SELECT value_num
FROM consistency_probe
WHERE id = 1;

COMMIT;
```

Trong phạm vi một hệ thống hứa strict serializability cho cả hai transaction, không có giao dịch thứ ba sửa hàng, `B` phải đọc được `1`. Nếu `B` đọc `0` và thực sự đã bắt đầu sau phản hồi commit của A, history là phản ví dụ cho lời hứa strict serializability của **đường truy cập được kiểm thử**.

Để phân tích chính xác cần ghi nhận:

- A và B đang kết nối tới đâu: primary, follower, cache hay một dịch vụ đứng trước database.
- Chế độ đọc: strong/linearizable hay explicitly stale/snapshot at time.
- Một lệnh `BEGIN` có thật sự bắt đầu transaction tại thời điểm mong muốn, hay driver/framework tạo snapshot sớm hoặc trễ hơn?
- A có thực sự nhận xác nhận **commit** chứ không phải nhận yêu cầu đang xử lý?
- Có transaction khác ghi lại `value_num` hay không?

Nếu kiểm thử với một DBMS đơn lẻ trên primary và luôn đọc giá trị mới, kết quả có thể luôn là `1`; điều đó không làm mất đi khác biệt lý thuyết giữa hai mức bảo đảm.

### 9.3. Kiểm tra nhiều hàng và giao dịch chồng lấn

Kiểm tra một khóa chưa chứng minh serializability trên nhiều hàng. Có thể bổ sung hai loại kịch bản:

**Chuyển tài sản giữa hai tài khoản.** T1 cập nhật cả `A` và `B` trong cùng transaction; T2 đọc cả hai trong một read-only transaction. Quan sát xem có lúc nào T2 thấy một nửa thay đổi không, sau khi đã loại trừ những trường hợp T2 cố ý dùng snapshot cũ.

**Write skew.** T1 và T2 cùng đọc điều kiện trên nhiều hàng rồi ghi những hàng khác nhau. Nếu cả hai commit và trạng thái cuối không có thứ tự tuần tự hợp lệ, lịch không serializable nên cũng không strictly serializable.

Ví dụ SQL minh họa kiểu write skew (cần điều phối hai session để chúng cùng đọc trước khi ghi):

```sql
-- Dữ liệu ban đầu: bác sĩ A và B đều có on_call = TRUE.
-- Mỗi session tự bắt đầu transaction.

SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;
-- Hai session cùng thấy 2.

-- Session T1:
UPDATE doctors
SET on_call = FALSE
WHERE id = 'A';

-- Session T2:
UPDATE doctors
SET on_call = FALSE
WHERE id = 'B';

-- Quan sát liệu cả hai COMMIT đều thành công hay
-- một transaction bị chờ, rollback hoặc báo lỗi xung đột.
```

Phép thử này phải gắn với isolation level và DBMS cụ thể; lịch đã mô tả là kịch bản để suy luận, không phải bảo đảm rằng mọi hệ sẽ cho cả hai commit.

### 9.4. Kiểm thử hữu hạn không thay thế chứng minh hợp đồng nhất quán

Một lần đọc sau ghi cho kết quả đúng chỉ cho thấy **lịch được kiểm thử** tương thích với strict serializability. Hệ phân tán có nhiều thứ tự giao dịch, sự cố kết nối, failover và đường định tuyến khác nhau. Để có cơ sở kết luận, cần kết hợp tài liệu bảo đảm của sản phẩm, cấu hình thật, đường đọc/ghi cụ thể, kiểm thử xen kẽ ở nhiều mức tải và cơ chế quan sát lỗi.

Ngược lại, chỉ cần **một lịch phản ví dụ đúng điều kiện** là đủ bác bỏ lời hứa strict serializability đối với phạm vi API đó.

## 10. Strict serializability đem lại điều gì cho ứng dụng?

Có ba nhóm tình huống dễ thấy lợi ích:

| Tình huống | Điều ứng dụng cần | Ý nghĩa của strict serializability |
|---|---|---|
| Client A xác nhận cập nhật xong, sau đó client B truy vấn cùng trạng thái | Bắt đầu đọc sau SUCCESS thì phải đọc trạng thái phù hợp với cập nhật đã xác nhận | Buộc thứ tự tuần tự giữ quan hệ A hoàn tất trước B bắt đầu. |
| Cập nhật nhiều hàng cùng một transaction | Người đọc không thấy một nửa giao dịch | Phần serializability bảo vệ tính tương đương tuần tự của giao dịch. |
| Quy trình nhiều bước phụ thuộc kết quả bước trước giữa các client | Bước sau không thể bị giải thích là đã chạy trước bước trước hoàn tất | Ràng buộc real-time bảo vệ quan hệ trước–sau được xác lập bên ngoài. |

Tuy nhiên, ngay cả strict serializability cũng **không tự động** mang lại:

- **Đúng mọi quy tắc nghiệp vụ:** nếu một transaction đơn lẻ vẫn cho phép số dư âm hoặc viết trạng thái sai, tuần tự hóa nghiêm ngặt không tự sửa logic.
- **Exactly-once request:** một client gửi lại yêu cầu sau timeout có thể tạo hai transaction hợp lệ; cần idempotency key hoặc ràng buộc thích hợp.
- **Atomicity xuyên dịch vụ bên ngoài:** thanh toán qua API, message broker hoặc email không tự tham gia transaction DB; cần outbox, saga hay giao thức tương ứng.
- **Khả dụng khi mạng chia cắt:** muốn duy trì tính nhất quán mạnh, hệ phân tán có thể phải từ chối hoặc trì hoãn một số thao tác khi không thể phối hợp an toàn.
- **Một snapshot mới nhất ở mọi nơi ngoài phạm vi cam kết:** dữ liệu ở cache, analytics, search index, read endpoint cho phép stale data không được tự coi là transaction strictly serializable.

Bảo đảm chỉ có ý nghĩa khi biết **đối tượng dữ liệu nào, loại transaction nào và endpoint nào nằm trong phạm vi**.

## 11. Những câu hỏi thường gặp

### Serializable có nhất thiết đọc được cập nhật vừa commit trước đó không?

**Chỉ từ định nghĩa serializability thì chưa kết luận được.** Một lịch đọc giá trị cũ có thể vẫn tương đương thứ tự tuần tự đặt transaction đọc trước transaction ghi, bất chấp thời gian thực. Trên một DBMS/cấu hình cụ thể, lời hứa về session, primary, snapshot hoặc external consistency có thể mạnh hơn và khiến lịch đó không xảy ra.

Nếu bài toán yêu cầu “đã nhận COMMIT OK rồi mới bắt đầu đọc thì phải thấy thay đổi”, hãy kiểm tra **strict serializability hoặc bảo đảm nhất quán đủ mạnh tương đương cho thao tác liên quan**, thay vì chỉ nhìn tên isolation.

### Nếu hai giao dịch chồng lấn, strict serializability có bắt buộc thứ tự bắt đầu không?

**Không.** Thứ tự bắt đầu của hai transaction chồng lấn không tự quyết định thứ tự tuần tự. Ràng buộc thời gian thực được áp dụng khi một giao dịch **hoàn tất trước khi giao dịch kia bắt đầu**. Những phụ thuộc dữ liệu hoặc cam kết API khác vẫn có thể ràng buộc thứ tự.

### Strict serializability có đồng nghĩa tất cả câu SELECT luôn thấy bản mới nhất tại giây nó chạy không?

**Không.** Với một read-only transaction đã bắt đầu trước khi giao dịch ghi kết thúc, mô hình có thể cho transaction đọc được tuyến tính hóa ở một thời điểm trước lần ghi, ngay cả khi một số câu SQL nội bộ chạy muộn hơn. Cần suy luận ở **ranh giới của toàn transaction**.

### Strict serializability có giống SQL SERIALIZABLE không?

**Không thể mặc định như vậy.** `SERIALIZABLE` là tên một mức cô lập theo SQL; hợp đồng sản phẩm về snapshot, định tuyến replica, thời điểm xác nhận commit và giao dịch phân tán phải được xem xét riêng. Có triển khai thực tế bảo đảm mạnh hơn định nghĩa serializability tối thiểu, nhưng không nên suy ra bảo đảm thời gian thực từ mỗi tên mức cô lập.

### Nếu mọi lần đọc/ghi từng hàng đều linearizable thì giao dịch nhiều hàng có strict serializability không?

**Chưa chắc.** Linearizability theo từng đối tượng không tự biến chuỗi nhiều thao tác thành **một transaction nguyên tử**. Hệ thống vẫn cần bảo đảm atomic visibility và serializable order cho **toàn bộ** đơn vị giao dịch.

### Strict serializability có cần đồng hồ toàn cầu chính xác tuyệt đối không?

**Không phải yêu cầu của định nghĩa.** Điều kiện là tôn trọng quan hệ trước–sau thực sự và đưa ra kết quả tương đương tuần tự. Triển khai phân tán có thể dùng phối hợp giữa node, đồng thuận, timestamp với sai số được kiểm soát, chờ an toàn hoặc kỹ thuật khác để đạt cam kết. Không thể chỉ lấy timestamp gắn ở client để thay thế chứng minh.

## 12. Bài tập suy luận lịch giao dịch

Giả sử `x = 0` ban đầu và không có transaction ghi nào khác ngoài `T1`:

**Lịch A**

```text
T1: BEGIN, WRITE(x=1), COMMIT, trả SUCCESS
T2:                                         BEGIN, READ(x)=0, COMMIT
```

Hai transaction **không chồng lấn**. Thứ tự `T2 → T1` có thể giải thích giá trị đọc theo serializability, nhưng trái với thứ tự thời gian thực. **Lịch A serializable nhưng không strictly serializable**.

**Lịch B**

```text
T1: BEGIN, WRITE(x=1) ------- COMMIT, SUCCESS
T2:       BEGIN ---------------- READ(x)=0, COMMIT
```

Hai transaction **chồng lấn**. Nếu không có phụ thuộc bổ sung, `T2 → T1` có thể giải thích giá trị đọc, đồng thời không vi phạm quan hệ real-time của hai giao dịch nguyên khối. **Lịch B có thể strictly serializable**, dù câu `READ` chạy sau lúc `T1` commit.

**Lịch C**

```text
T1: BEGIN, WRITE(x=1), COMMIT, SUCCESS
T2:                                        BEGIN, READ(x)=1, COMMIT
```

Thứ tự tuần tự `T1 → T2` vừa cho kết quả đọc đúng vừa giữ real-time order. **Lịch C phù hợp với strict serializability**.

**Lịch D**

Hai giao dịch write skew cùng đọc hai bác sĩ đều đang trực, rồi mỗi bên cho một bác sĩ nghỉ, cả hai commit. Nếu thứ tự tuần tự nào cũng sẽ khiến một giao dịch không được cho người cuối cùng nghỉ theo chính phép kiểm tra nghiệp vụ của nó, thì **lịch D không serializable**; vì vậy cũng không strictly serializable. Đổi cách sắp xếp theo thời gian thực không cứu được một lịch vốn không có thứ tự tuần tự hợp lệ.

## 13. Ghi nhớ

**Serializability** là khả năng giải thích kết quả của các transaction như thể chúng được thực hiện trong một thứ tự tuần tự nào đó. **Strict serializability** bổ sung yêu cầu thứ tự ấy phải tôn trọng sự kiện ngoài hệ thống: **transaction đã hoàn tất trước khi transaction khác bắt đầu thì phải đứng trước**.

Hai điểm phân biệt giúp tránh nhầm lẫn: **chạy chồng lấn vẫn có thể strictly serializable**, và **giao dịch đã commit nhưng transaction bắt đầu sau vẫn đọc snapshot cũ có thể là serializable nhưng không strictly serializable**. Khi áp dụng cho dịch vụ thật, phải xác định rõ phạm vi API, ý nghĩa của response thành công, chính sách replica/snapshot, và toàn bộ ranh giới transaction được bảo vệ.
