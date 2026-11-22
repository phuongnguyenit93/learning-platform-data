# Lịch không đọc dữ liệu chưa xác nhận và lịch nghiêm ngặt

Trong cơ sở dữ liệu có nhiều giao dịch thực thi đồng thời, **thứ tự xen kẽ các thao tác** quyết định một giao dịch có nhìn thấy thay đổi chưa được xác nhận của giao dịch khác hay không và hệ thống sẽ phải làm gì nếu một giao dịch thất bại. Hai khái niệm quan trọng trong mô hình lịch thực thi là:

- **Lịch không đọc dữ liệu chưa xác nhận (cascadeless schedule, hay lịch tránh hủy dây chuyền):** một giao dịch chỉ đọc kết quả do giao dịch khác ghi sau khi giao dịch ghi **COMMIT**.
- **Lịch nghiêm ngặt (strict schedule):** sau khi một giao dịch ghi một mục dữ liệu, các giao dịch khác **không được đọc hoặc ghi đè mục ấy** cho đến khi giao dịch ghi **COMMIT hoặc ROLLBACK**.

Cả hai cùng giúp việc phục hồi an toàn hơn, nhưng lịch nghiêm ngặt đặt ra điều kiện mạnh hơn. Để thấy rõ khác biệt, cần phân biệt **đọc bẩn (dirty read)**, **ghi bẩn (dirty write)** và **phụ thuộc commit**.

## 1. Lịch thực thi là gì?

Một **giao dịch (transaction)** là đơn vị công việc gồm các thao tác đọc, ghi và một kết thúc bằng **COMMIT** hoặc **ABORT/ROLLBACK**. Khi có nhiều giao dịch, DBMS có thể xen kẽ thao tác của chúng thay vì chạy xong toàn bộ giao dịch này rồi mới chạy giao dịch khác.

Một **lịch thực thi (schedule/history)** mô tả thứ tự các thao tác đó, đồng thời giữ nguyên thứ tự nội bộ của từng giao dịch.

Ta dùng ký hiệu:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| \`T1\`, \`T2\` | Giao dịch số 1, số 2 |
| \`r1(X)\` | T1 đọc mục dữ liệu X |
| \`w1(X)\` | T1 ghi mục dữ liệu X |
| \`c1\` | T1 COMMIT thành công |
| \`a1\` | T1 ABORT/ROLLBACK |
| \`r2(X) ← w1(X)\` | T2 đọc giá trị/phiên bản X do T1 tạo ra |
| \`X\`, \`Y\` | Mục dữ liệu, ví dụ một hàng hoặc phần tử logic cần phân tích |

Trong ký hiệu ngắn gọn, lịch:

~~~text
S = w1(X)  r2(X)  c1  c2
~~~

có nghĩa: T1 ghi X, T2 đọc X, T1 commit, cuối cùng T2 commit. **Nếu r2(X) thực sự đọc giá trị vừa được w1(X) tạo ra**, T2 đã đọc dữ liệu chưa commit tại thời điểm đọc. Lịch này có vấn đề dù cuối cùng cả hai giao dịch đều commit.

Trong mô hình lịch cổ điển thường xét **một phiên bản logic của mỗi mục dữ liệu**. Với DBMS hỗ trợ **MVCC**, một lệnh SELECT có thể đọc phiên bản X đã commit cũ hơn trong khi phiên bản mới do giao dịch khác ghi vẫn chưa commit. Vì vậy, khi phân tích hệ thống thực tế, phải xác định **T2 đọc phiên bản nào**, không chỉ thấy hai câu SQL cùng nhắc tới X.

### Lịch tuần tự và lịch xen kẽ

Lịch tuần tự:

~~~text
T1: r1(X) → w1(X) → c1
T2:                    r2(X) → w2(X) → c2
~~~

Lịch xen kẽ:

~~~text
T1: r1(X) → w1(X) --------→ c1
T2:               r2(X) --------→ c2
~~~

Lịch xen kẽ chưa chắc sai; nó chỉ cần thỏa những điều kiện phù hợp với mục tiêu như cô lập, phục hồi, khả năng tránh deadlock và hiệu năng. Một lịch có thể bảo đảm an toàn phục hồi nhưng vẫn có lỗi logic do cạnh tranh.

## 2. Đọc dữ liệu chưa xác nhận: dirty read

**Dirty read** xảy ra khi T2 đọc giá trị do T1 ghi **trước khi T1 commit**, rồi giá trị ấy có thể bị T1 hủy bằng rollback.

Ví dụ số dư ban đầu X = 1.000:

~~~text
Thời điểm      T1                               T2
   1       w1(X = 900)
   2                                        r2(X) → 900
   3       a1 (ROLLBACK)
   4                                        T2 đã dùng 900 để tính toán
~~~

Nếu T2 đã tính phí, lập báo cáo hoặc tiếp tục cập nhật Y dựa trên 900, kết quả ấy xuất phát từ một giá trị **chưa bao giờ trở thành dữ liệu đã commit**.

~~~mermaid
sequenceDiagram
    participant T1 as Giao dịch T1
    participant DB as Mục dữ liệu X
    participant T2 as Giao dịch T2
    T1->>DB: w1(X = 900), chưa COMMIT
    DB-->>T2: r2(X) = 900, dirty read
    T1->>DB: ROLLBACK
    Note over T2: Giá trị 900 đã bị hủy
~~~

Đọc bẩn tạo ra **phụ thuộc vào một giao dịch chưa được xác nhận**. Nếu T1 rollback, T2 không thể tiếp tục coi kết quả tính toán dựa trên 900 là hợp lệ.

### Hủy dây chuyền (cascading abort)

Xét ba giao dịch:

~~~text
S = w1(X)  r2(X)  w2(Y)  r3(Y)  a1  a2  a3
~~~

Diễn giải:

1. T1 ghi X nhưng chưa commit.
2. T2 đọc X từ T1 và dùng nó để tạo Y; T2 cũng chưa commit.
3. T3 đọc Y từ T2, tiếp tục tính toán.
4. T1 rollback, làm giá trị X mà T2 đã đọc không hợp lệ.
5. T2 phải rollback những kết quả phụ thuộc X.
6. T3 lại phụ thuộc Y do T2 tạo ra, nên cũng phải rollback.

~~~mermaid
flowchart LR
    A["T1 ghi X<br/>chưa commit"] -->|T2 đọc X| B["T2 ghi Y<br/>chưa commit"]
    B -->|T3 đọc Y| C["T3 tiếp tục xử lý"]
    D["T1 ROLLBACK"] -.-> E["T2 phải ROLLBACK"]
    E -.-> F["T3 phải ROLLBACK"]
~~~

**Cascading abort** nghĩa là việc hủy một giao dịch kéo theo việc hủy những giao dịch khác vì chúng đã sử dụng dữ liệu chưa commit của nó. Việc này làm tăng chi phí phục hồi và khiến lượng công việc bị mất lan rộng.

Nếu T2 **đã commit** trước khi biết T1 phải rollback, vấn đề còn nghiêm trọng hơn: cơ chế rollback thông thường không thể đơn giản “rút lại” một giao dịch đã commit như thể nó chưa xảy ra. Vì vậy, ta còn cần khái niệm **lịch có thể phục hồi (recoverable schedule)**.

## 3. Lịch có thể phục hồi (recoverable schedule)

Một lịch là **recoverable** nếu, mỗi khi T2 đọc một giá trị do T1 ghi, **T2 không được commit trước khi T1 commit**. Nói cách khác, giao dịch phụ thuộc vào kết quả của giao dịch khác phải chờ giao dịch nguồn được xác nhận trước khi tự xác nhận.

Biểu diễn điều kiện khi T2 đọc từ T1:

~~~text
Nếu r2(X) đọc từ w1(X), và cả T1 lẫn T2 commit:
    c1 phải đứng trước c2.
~~~

Lịch sau **recoverable**:

~~~text
S1 = w1(X)  r2(X)  c1  c2
                ↑
          T2 đọc bẩn,
          nhưng T2 chờ T1 commit trước khi commit.
~~~

Lịch này vẫn **cho phép dirty read**. Nếu T1 rollback trước khi commit, T2 buộc phải hủy phần công việc phụ thuộc để duy trì khả năng phục hồi; rollback có thể lan dây chuyền.

Ngược lại, lịch sau **không recoverable**:

~~~text
S2 = w1(X)  r2(X)  c2  a1
                     ↑
            T2 commit dựa trên dữ liệu
            mà T1 sau đó rollback.
~~~

T2 đã chốt kết quả dựa trên dữ liệu của T1 trong khi T1 chưa xác nhận. Khi T1 rollback, chỉ thao tác rollback thông thường không đủ để đảo ngược giao dịch T2 đã commit. Lịch này **non-recoverable**.

Điểm quan trọng: **recoverable không có nghĩa tránh được cascading abort**. Nó chỉ bảo đảm không xác nhận một giao dịch trước giao dịch mà nó đã đọc dữ liệu từ đó. Lịch không đọc dữ liệu chưa xác nhận đặt ra một điều kiện mạnh hơn.

## 4. Lịch không đọc dữ liệu chưa xác nhận (cascadeless schedule)

Một lịch **cascadeless**, còn gọi là **avoids cascading aborts (ACA)**, là lịch mà **mỗi giao dịch chỉ được đọc giá trị do giao dịch khác ghi sau khi giao dịch ghi đã commit**.

Điều kiện với hai giao dịch khác nhau:

~~~text
Nếu r2(X) đọc phiên bản X do w1(X) tạo:
    w1(X) → c1 → r2(X)
~~~

Nói cách khác, **COMMIT của giao dịch tạo ra giá trị phải có trước lần đọc giá trị đó**. Một giao dịch được phép đọc các giá trị do chính nó vừa ghi; hạn chế này nhắm đến việc đọc từ **giao dịch khác**.

### Ví dụ lịch cascadeless

~~~text
S3 = w1(X)  r2(Y)  c1  r2(X)  c2
~~~

Giả sử T1 chỉ ghi X, còn Y không bị T1 thay đổi. T2 có thể đọc Y trong khi T1 đang hoạt động. Tuy nhiên, T2 chỉ đọc **X do T1 tạo ra sau c1**; vì vậy không có dirty read đối với X.

~~~text
Thời gian ───────────────────────────────────────────────>

T1:      w1(X) ───────────────── c1
T2:                r2(Y) ──────────── r2(X) ─── c2
                                    ▲
                         Chỉ đọc X sau COMMIT T1
~~~

Nếu T1 rollback thay vì commit, T2 có thể tiếp tục làm việc khác mà **không dùng giá trị chưa commit của T1**. Kết quả chưa được xác nhận của T1 không trở thành đầu vào cho T2.

### Tại sao cascadeless ngăn cascading abort?

Trong ví dụ hủy dây chuyền, nguyên nhân gây lây lan là cạnh \`T1 → T2\`: T2 đọc X khi T1 chưa commit. Với cascadeless, T2 chỉ có thể đọc X sau khi T1 đã commit. Nếu T1 rollback, T2 chưa từng được phép đọc kết quả chưa commit của T1. Chuỗi phụ thuộc bẩn vì thế không hình thành.

~~~text
Không cascadeless:
T1 ghi X chưa commit → T2 đọc X → T3 đọc kết quả T2 → T1 hủy
                                             ↳ có thể hủy dây chuyền

Cascadeless:
T1 ghi X → T1 commit → T2 đọc X → T2 tạo kết quả → T3 đọc sau T2 commit
           ↑
     Đã xác nhận trước khi thành dữ liệu nguồn.
~~~

Đây là lý do lịch cascadeless hỗ trợ phục hồi dễ hơn lịch chỉ recoverable: giao dịch không cần bị hủy **chỉ vì đã đọc một giá trị chưa commit của giao dịch khác**.

Tuy nhiên, **cascadeless chỉ kiểm soát thao tác đọc**. Nó không mặc nhiên cấm giao dịch khác **ghi đè** một giá trị chưa commit.

## 5. Ghi đè dữ liệu chưa xác nhận: dirty write

**Dirty write** xảy ra khi T2 ghi lên cùng một mục X đã được T1 ghi, trong khi T1 **chưa commit hoặc rollback**. Điều này khác với dirty read: T2 có thể không hề đọc X mà vẫn ghi đè X.

Ví dụ:

~~~text
X ban đầu = 100

S4 = w1(X = 90)  w2(X = 80)  c1  c2
~~~

Ở thời điểm \`w2(X)\`, T1 vẫn chưa kết thúc. T2 ghi lên X đang có thay đổi chưa được xác nhận của T1. Lịch này:

- **Không có dirty read** giữa các giao dịch, vì không xuất hiện thao tác đọc từ bản ghi chưa commit.
- **Là cascadeless** theo định nghĩa điều kiện đọc (trường hợp không có quan hệ đọc dữ liệu bẩn).
- **Không phải strict**, bởi có \`w2(X)\` trước khi T1 kết thúc.

Đây là phản ví dụ cho nhận định “không đọc bẩn thì cũng không ghi bẩn”.

### Vì sao dirty write gây khó phục hồi?

Giả sử sau khi T2 ghi đè, T1 rollback. Khi hệ thống muốn hoàn tác thay đổi của T1, phải tránh phá hủy thay đổi còn đang thuộc T2. Nếu T2 commit trước hoặc đang có các thao tác khác phụ thuộc X, phục hồi càng phức tạp.

~~~text
w1(X = 90) → w2(X = 80) → a1 → ...
                ▲
      T2 ghi trong lúc thay đổi của T1 còn chưa chốt.
~~~

Thực tế DBMS có thể dùng khóa ghi, MVCC, kiểm tra xung đột và log để không cho lịch bẩn này xảy ra hoặc để xử lý nó một cách an toàn. Mục đích ở đây là hiểu **điều kiện lý thuyết**: chỉ cấm dirty read chưa đủ để loại trừ dirty write.

## 6. Lịch nghiêm ngặt (strict schedule)

Một lịch **strict** là lịch thỏa quy tắc sau:

> Khi T1 đã ghi X, không giao dịch khác nào được **đọc X hoặc ghi X** cho đến khi T1 **COMMIT hoặc ABORT**.

Theo mô hình một phiên bản:

~~~text
T1:    w1(X) --------------------- c1 hoặc a1
T2:          r2(X) hoặc w2(X)       chỉ được thực hiện sau mốc này
             ↑
         KHÔNG được phép ở khoảng T1 chưa kết thúc
~~~

Điều kiện strict áp dụng theo **mục dữ liệu đã được ghi**. Nó không khóa toàn bộ cơ sở dữ liệu: nếu T1 chỉ ghi X, T2 vẫn có thể truy cập mục Y độc lập, theo các hạn chế khác của DBMS.

Lịch strict cấm cả hai loại phụ thuộc vào thay đổi chưa commit:

1. **Dirty read:** T2 không đọc bản ghi X mới của T1 trước c1/a1.
2. **Dirty write:** T2 không ghi đè lên X khi thay đổi của T1 chưa được chốt.

### Ví dụ strict khi T1 commit

~~~text
S5 = w1(X)  r2(Y)  c1  r2(X)  w2(X)  c2
~~~

T2 đọc Y khi T1 chưa kết thúc, nhưng X chỉ được đọc và ghi bởi T2 **sau khi T1 commit**. Lịch strict cho phép các thao tác trên dữ liệu không liên quan xen kẽ.

| Bước | T1 | T2 | Có hợp lệ với strict? |
| --- | --- | --- | --- |
| 1 | \`w1(X)\` | | Có: T1 đang sửa X |
| 2 | | \`r2(Y)\` | Có: Y không bị T1 ghi |
| 3 | \`c1\` | | Có: thay đổi X được xác nhận |
| 4 | | \`r2(X)\` | Có: T1 đã kết thúc |
| 5 | | \`w2(X)\` | Có: không còn ghi X chưa commit từ T1 |
| 6 | | \`c2\` | Có: T2 kết thúc |

### Ví dụ strict khi T1 rollback

~~~text
S6 = w1(X)  r2(Y)  a1  r2(X)  w2(X)  c2
~~~

T2 phải chờ T1 hủy thay đổi X trước khi có thể truy cập X. Sau \`a1\`, T2 đọc phiên bản X đã phục hồi; nó không tiếp nhận giá trị đã bị hủy của T1. Điều này giảm đáng kể số trường hợp cần phối hợp hoàn tác giữa các giao dịch.

### Ví dụ không strict nhưng cascadeless

Nhắc lại:

~~~text
S4 = w1(X)  w2(X)  c1  c2
~~~

S4 **cascadeless** vì không có dirty read, nhưng **vi phạm strict** ngay tại \`w2(X)\`: T1 đã ghi X mà chưa kết thúc. Đây là khác biệt quyết định giữa hai lớp lịch.

## 7. Quan hệ giữa recoverable, cascadeless và strict

Ba lớp lịch tạo thành quan hệ bao hàm:

~~~mermaid
flowchart TD
    A["STRICT<br/>Không đọc bẩn, không ghi bẩn"] --> B["CASCADELESS / ACA<br/>Không đọc bẩn"]
    B --> C["RECOVERABLE<br/>Không commit trước giao dịch đã đọc dữ liệu từ đó"]
~~~

Tức là:

~~~text
STRICT ⊂ CASCADELESS ⊂ RECOVERABLE
~~~

Ký hiệu \`⊂\` ở đây thể hiện bao hàm thực sự: có lịch recoverable không cascadeless, và có lịch cascadeless không strict.

**Vì sao strict kéo theo cascadeless?** Nếu T1 đã ghi X, strict cấm T2 đọc X cho tới khi T1 commit hoặc abort. Trong trường hợp T2 đọc phiên bản do T1 tạo ra, T1 bắt buộc đã commit; điều kiện cascadeless được thỏa.

**Vì sao cascadeless kéo theo recoverable?** Nếu T2 chỉ đọc X của T1 sau khi T1 commit thì lúc T2 commit, c1 tất nhiên đã xảy ra trước đó. Điều kiện recoverable được thỏa.

**Vì sao chiều ngược lại không đúng?** Recoverable cho phép T2 đọc dữ liệu chưa commit nếu T2 đợi T1 commit trước khi tự commit. Cascadeless cho phép T2 ghi đè dữ liệu chưa commit nếu không vi phạm điều kiện đọc.

| Lớp lịch | Dirty read | Dirty write | Cascading abort do đọc bẩn | T2 có thể commit trước T1 khi T2 đã đọc từ T1? |
| --- | --- | --- | --- | --- |
| **Recoverable** | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra | **Không** |
| **Cascadeless / ACA** | **Không** | Có thể xảy ra | **Không** | **Không** |
| **Strict** | **Không** | **Không** | **Không** | **Không** |

Những ô “có thể xảy ra” là điều **định nghĩa lớp lịch chưa loại trừ**, không có nghĩa DBMS cụ thể chắc chắn cho phép thao tác đó.

### Bốn lịch để phân loại nhanh

| Lịch | Recoverable? | Cascadeless? | Strict? | Lý do chính |
| --- | --- | --- | --- | --- |
| \`w1(X) r2(X) c2 a1\` | Không | Không | Không | T2 commit trước T1, rồi T1 abort |
| \`w1(X) r2(X) c1 c2\` | Có | Không | Không | T2 đọc X trước c1 nhưng chờ c1 mới commit |
| \`w1(X) w2(X) c1 c2\` | Có | Có | Không | Không đọc bẩn, nhưng có dirty write |
| \`w1(X) c1 r2(X) w2(X) c2\` | Có | Có | Có | T2 đọc/ghi X sau c1 |

Từ bảng này có thể nhận ra: **cascadeless là điều kiện trên thời điểm đọc; strict là điều kiện trên cả thời điểm đọc và ghi sau một lần ghi chưa được xác nhận**.

## 8. Strict giúp việc UNDO và REDO dễ kiểm soát như thế nào?

Khi giao dịch thất bại, cơ chế phục hồi thường phải phân biệt:

- Thay đổi của **giao dịch đã commit** cần được giữ lại; tùy trạng thái trang dữ liệu, có thể cần REDO.
- Thay đổi của **giao dịch chưa commit** cần được hủy, hoặc không được trở thành kết quả đã xác nhận.

Nếu một giao dịch khác đã ghi đè một giá trị chưa commit, việc hoàn tác thay đổi ban đầu phải cẩn thận để không loại bỏ giá trị mới thuộc một giao dịch khác.

### Tình huống với dirty write

~~~text
X = 100

w1(X = 90)
w2(X = 80)   <-- T2 ghi đè trước khi T1 commit/abort
a1           <-- cần UNDO T1 khi T2 vẫn còn liên quan đến X
~~~

Với lịch strict, thao tác \`w2(X)\` **phải chờ** T1 kết thúc, nên không hình thành kiểu chồng lấn ghi chưa commit này.

~~~text
X = 100

w1(X = 90)
a1             <-- khôi phục trạng thái của T1
w2(X = 80)     <-- T2 ghi sau khi T1 đã kết thúc
c2
~~~

Lợi ích chính của strict là **không để giao dịch khác sử dụng hoặc ghi đè trực tiếp kết quả ghi chưa chốt**. Vì vậy, khi T1 rollback, DBMS không phải hủy dây chuyền những giao dịch đã đọc giá trị chưa commit của T1, cũng không phải xử lý xung đột dirty write trong lịch này.

Điều này **không loại bỏ nhu cầu WAL/redo/undo log**. Strict là tính chất về thứ tự thao tác; hệ thống vẫn cần cơ chế phục hồi bền vững khi process crash, mất điện hoặc lỗi thiết bị. Cách DBMS ghi nhật ký và tái dựng trạng thái còn phụ thuộc kiến trúc thực tế.

## 9. Strict có giống serializable không?

**Không.** Strict và serializable giải quyết hai câu hỏi khác nhau:

- **Strict:** một giao dịch khác có được chạm vào mục dữ liệu mà T1 **đã ghi nhưng chưa kết thúc** hay không?
- **Serializable:** kết quả của lịch xen kẽ có tương đương một lịch tuần tự hợp lệ theo tiêu chuẩn serializability được xét hay không?

Một lịch **có thể strict nhưng không conflict-serializable**.

### Phản ví dụ: lịch strict nhưng có chu trình phụ thuộc

Giả sử X và Y là hai mục dữ liệu độc lập, ban đầu đều bằng 0. Hai giao dịch đọc cả X và Y, sau đó mỗi giao dịch ghi một mục khác nhau:

~~~text
S7 =
    r1(X)
    r2(X)
    r1(Y)
    r2(Y)
    w1(X)
    w2(Y)
    c1
    c2
~~~

Lịch này **strict** vì:

- Sau \`w1(X)\`, không có giao dịch khác đọc hoặc ghi X trước \`c1\`.
- Sau \`w2(Y)\`, không có giao dịch khác đọc hoặc ghi Y trước \`c2\`.
- Các lần đọc \`r1(X)\`, \`r2(X)\`, \`r1(Y)\`, \`r2(Y)\` đều diễn ra **trước** các lần ghi chưa commit của giao dịch kia, nên không đọc bẩn.

Tuy nhiên, xét **đồ thị xung đột (precedence graph)**:

- \`r2(X)\` đứng trước \`w1(X)\` nên có cạnh **T2 → T1**.
- \`r1(Y)\` đứng trước \`w2(Y)\` nên có cạnh **T1 → T2**.

~~~mermaid
flowchart LR
    A["T1"] -->|r1(Y) trước w2(Y)| B["T2"]
    B -->|r2(X) trước w1(X)| A
~~~

Có chu trình **T1 → T2 → T1**, vì vậy lịch **không conflict-serializable**.

Phân biệt này rất quan trọng trong các bài toán như write skew: không đọc bẩn và không ghi bẩn vẫn chưa đủ để bảo đảm mọi ràng buộc nghiệp vụ khi hai giao dịch dựa trên những lần đọc chồng lấn.

### Strict two-phase locking khác strict schedule

Một kỹ thuật triển khai thường gặp là **strict two-phase locking (strict 2PL)**:

1. Trong pha tăng trưởng, giao dịch lấy các khóa cần thiết.
2. Khi bắt đầu nhả khóa, nó không lấy thêm khóa theo quy tắc 2PL.
3. Các **khóa ghi độc quyền (X-lock)** được giữ đến COMMIT/ROLLBACK.

Strict 2PL vừa tạo lịch **strict**, vừa bảo đảm **conflict serializability** khi các thao tác được điều phối đúng theo giao thức khóa. Tuy nhiên, tên “strict 2PL” mô tả **một giao thức điều khiển đồng thời**; “strict schedule” mô tả **tính chất của một lịch đã hình thành**. Hai thuật ngữ không đồng nghĩa.

Giữ khóa độc quyền đến khi kết thúc có thể khiến giao dịch khác phải chờ lâu, phát sinh deadlock hoặc giảm tính đồng thời. DBMS cần chính sách phát hiện/giải quyết deadlock và quản lý transaction đủ ngắn để giảm chi phí.

## 10. Liên hệ với isolation level, khóa và MVCC

Các mức cô lập như **READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE** là những lựa chọn của DBMS về khả năng quan sát và xung đột. Chúng không đồng nhất từng chữ với các lớp lịch recoverable/cascadeless/strict.

### READ COMMITTED thường ngăn dirty read

Ở mức READ COMMITTED, một giao dịch không được thấy dữ liệu chưa commit của giao dịch khác theo ngữ nghĩa dirty read. Điều đó tương ứng với **mục tiêu cascadeless về thao tác đọc**, nhưng **chưa đủ để kết luận toàn bộ lịch thực tế là strict** theo định nghĩa cổ điển.

Nhiều DBMS còn dùng cơ chế khóa ghi hoặc phát hiện xung đột để ngăn ghi đè chưa commit; muốn đánh giá strictness thực tế cần xem cả **đường ghi**, chứ không suy từ tên isolation level.

Một số DBMS có quy tắc riêng: ví dụ PostgreSQL xử lý yêu cầu READ UNCOMMITTED bằng hành vi READ COMMITTED. Do đó, tên mức cô lập trong SQL không chứng minh rằng dirty read thực sự xảy ra.

### Locking và truy cập trên cùng mục dữ liệu

Một cơ chế dựa trên khóa có thể thực thi quy tắc gần với strict bằng cách giữ **exclusive lock** trên X từ khi ghi đến khi commit/rollback:

~~~text
T1:  X-lock(X) ─ w1(X) ───────────────── c1 ─ unlock(X)
T2:                 muốn r2(X)/w2(X) ── chờ ──> thực hiện
~~~

Với mô hình một phiên bản, giữ khóa ghi như vậy ngăn giao dịch khác đọc hoặc ghi X đang bị cập nhật chưa commit. Trong hệ thống có MVCC, truy vấn thường có thể đọc phiên bản đã commit trước đó mà **không đợi** khóa ghi đang giữ trên phiên bản mới.

### MVCC: đọc phiên bản cũ đã commit

Giả sử X có phiên bản đã commit \`X@v1 = 100\`. T1 tạo phiên bản mới \`X@v2 = 90\` nhưng chưa commit:

~~~text
Phiên bản đã commit:   X@v1 = 100
Phiên bản của T1:      X@v2 = 90 (chưa commit)

T2 SELECT X  ───────────────> có thể đọc X@v1 = 100
                                thay vì đọc X@v2 = 90
~~~

T2 đọc X trong lúc T1 đang ghi X, nhưng **không phải dirty read** vì T2 không đọc phiên bản chưa commit của T1. Khi diễn giải lịch theo MVCC, quan hệ **read-from** giữa các **phiên bản** mới quyết định T2 phụ thuộc vào giao dịch nào.

Do đó, không nên kết luận “hễ SELECT không chờ UPDATE thì DBMS cho phép dirty read”. Cũng không nên áp máy móc biểu diễn strict của mô hình **một phiên bản** lên từng câu SQL trên hệ MVCC mà bỏ qua việc T2 thực sự đọc phiên bản nào.

Các DBMS MVCC thường kết hợp version visibility với khóa hoặc kiểm tra xung đột trên đường ghi. Tính chất phục hồi thực tế phải đánh giá trên **phiên bản, thứ tự commit và xung đột ghi** mà DBMS cho phép.

## 11. Cách phân loại một lịch trên giấy

Khi gặp bài tập phân loại lịch thực thi, có thể làm theo thứ tự:

1. **Đánh dấu các thao tác của từng transaction:** \`r_i(X)\`, \`w_i(X)\`, \`c_i\`, \`a_i\`.
2. **Xác định read-from:** mỗi lần đọc thuộc Tj lấy dữ liệu từ phiên bản nào, do Ti tạo hay từ trạng thái đã commit trước đó?
3. **Kiểm tra recoverable:** nếu Tj đọc từ Ti, Tj có commit **sau** Ti không? Nếu Tj commit trước Ti hoặc Ti rollback sau khi Tj đã commit, lịch không recoverable.
4. **Kiểm tra cascadeless:** có lần đọc nào lấy giá trị do giao dịch khác ghi **trước commit của giao dịch ghi** không? Nếu có, lịch không cascadeless.
5. **Kiểm tra strict:** sau mỗi \`w_i(X)\`, trước \`c_i\` hoặc \`a_i\`, có \`r_j(X)\` hay \`w_j(X)\` với \`j ≠ i\` không? Nếu có, lịch không strict.
6. **Nếu đề yêu cầu serializability:** dựng thêm đồ thị xung đột hoặc dùng phương pháp phù hợp; không suy serializability từ strictness.

### Ví dụ tổng hợp

Xét lịch:

~~~text
S8 = r1(A)  w1(B)  r2(A)  w2(C)  c2  c1  r3(B)  c3
~~~

- T1 ghi **B** trước \`c1\`.
- T2 đọc **A** và ghi **C**, không đọc hoặc ghi B.
- T3 đọc B **sau** khi T1 đã commit.
- Không xuất hiện read-from của giá trị chưa commit giữa các giao dịch.
- Không giao dịch khác truy cập B trong thời gian T1 đã ghi B nhưng chưa kết thúc; tương tự với C của T2.

**S8 là strict**, do đó cũng cascadeless và recoverable. T2 được commit trước T1 dù hai giao dịch xen kẽ, vì **T2 không đọc dữ liệu do T1 ghi**; strict không yêu cầu mọi transaction phải commit theo thứ tự bắt đầu.

Thử biến đổi chỉ một thao tác:

~~~text
S9 = r1(A)  w1(B)  r2(B)  w2(C)  c1  c2
                        ▲
                 T2 đọc B trước c1
~~~

**S9 recoverable** vì \`c1\` đứng trước \`c2\`, nhưng **không cascadeless và không strict** do \`r2(B)\` đọc từ lần ghi chưa commit \`w1(B)\`.

Một biến đổi khác:

~~~text
S10 = r1(A)  w1(B)  w2(B)  c1  c2
                         ▲
                 T2 ghi B trước c1
~~~

**S10 cascadeless** vì không có lần đọc bẩn, nhưng **không strict** vì có dirty write.

### Bài tập tự kiểm tra

**Bài 1.** Phân loại lịch:

~~~text
w1(X)  r2(Y)  c1  r2(X)  c2
~~~

**Đáp án:** Strict; các thao tác của T2 trên X xuất hiện sau \`c1\`, còn lần đọc Y không liên quan đến giá trị X chưa commit.

**Bài 2.** Phân loại lịch:

~~~text
w1(X)  r2(X)  a1  a2
~~~

**Đáp án:** Không cascadeless và không strict vì T2 đã đọc X chưa commit của T1. T2 rollback theo T1, minh họa cascading abort. Không có commit sai thứ tự, nên điều kiện recoverable không bị vi phạm trong lịch kết thúc bằng hai lần abort này.

**Bài 3.** Phân loại lịch:

~~~text
w1(X)  w2(Y)  c2  c1
~~~

**Đáp án:** Strict, nếu X và Y độc lập và không còn thao tác nào khác. T2 ghi Y trong khi T1 chưa commit X nhưng không truy cập mục X chưa commit.

**Bài 4.** T1 đã ghi X, T2 đọc phiên bản X **đã commit trước đó** trong hệ MVCC. Có phải dirty read không?

**Đáp án:** Không. Dirty read yêu cầu T2 đọc dữ liệu chưa commit của T1. Khi mô hình hóa lịch theo một phiên bản, cần điều chỉnh biểu diễn để phản ánh phiên bản mà T2 thực sự đọc.

**Bài 5.** Một lịch là strict. Có thể kết luận nó conflict-serializable không?

**Đáp án:** Không. Strict không ngăn tất cả chu trình phụ thuộc do những lần đọc trước các thao tác ghi; cần kiểm tra serializability riêng.

## 12. Ý nghĩa thực tế với ứng dụng đồng thời

Khi ứng dụng Java/Spring làm việc với cơ sở dữ liệu, mục tiêu không phải tự tay sắp xếp từng \`r_i(X)\` và \`w_i(X)\`; DBMS đã cung cấp cơ chế giao dịch, khóa, MVCC và phục hồi. Nhưng mô hình lịch giúp đặt câu hỏi đúng khi điều tra lỗi:

- Một SELECT đang thấy giá trị **đã commit** hay phiên bản mới chưa commit của giao dịch khác?
- Một UPDATE có thể ghi đè khi transaction khác vẫn giữ thay đổi chưa chốt trên cùng hàng không?
- Khi một transaction rollback, những transaction khác có cần bị hủy vì đã dùng dữ liệu của nó không?
- Hệ thống có giữ khả năng phục hồi nhưng vẫn gặp **lost update, write skew hoặc non-repeatable read** không?
- Isolation level, khóa, MVCC và chính sách retry thực sự bảo đảm thuộc tính nào?

Ví dụ đặt hàng có hai giao dịch cùng giảm tồn kho: việc tránh dirty read và dirty write là điều kiện an toàn cơ bản, nhưng vẫn cần kiểm tra cách cập nhật số lượng, ràng buộc không âm, mức cô lập và chiến lược retry khi có xung đột. Một lịch strict vẫn có thể cho kết quả sai so với quy tắc nghiệp vụ nếu ứng dụng bỏ qua những phụ thuộc do đọc trước và ghi sau.

**Phân biệt cần nhớ:** lịch **recoverable** kiểm soát **thứ tự COMMIT khi có phụ thuộc đọc**; lịch **cascadeless** cấm **đọc dữ liệu chưa commit từ giao dịch khác**; lịch **strict** cấm **cả đọc lẫn ghi lên mục đã được giao dịch khác ghi nhưng chưa kết thúc**. Quan hệ bao hàm \`strict ⇒ cascadeless ⇒ recoverable\` giúp nhận diện mức độ an toàn phục hồi, còn **serializability** là tiêu chí bổ sung phải đánh giá độc lập.
