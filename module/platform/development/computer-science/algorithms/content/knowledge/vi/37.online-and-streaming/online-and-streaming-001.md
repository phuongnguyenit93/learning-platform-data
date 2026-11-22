# Thuật toán trực tuyến khi chưa biết dữ liệu tương lai

## 1. Bối cảnh: phải quyết định trước khi biết hết đầu vào

Trong thuật toán ngoại tuyến (*offline*), ta thường có toàn bộ dữ liệu trước khi tính toán. Chẳng hạn muốn xếp lịch 1.000 công việc lên các máy, thuật toán ngoại tuyến được xem toàn bộ thời lượng rồi mới quyết định phân công. Thuật toán trực tuyến (*online algorithm*) nhận các sự kiện lần lượt và **phải đưa ra quyết định khi dữ liệu tương lai chưa có**.

Các tình huống thực tế:

- Hôm nay cần thuê hay mua thiết bị, chưa biết còn sử dụng bao nhiêu ngày.
- Công việc mới tới cần gán ngay cho máy, chưa biết các công việc ngày mai.
- Một trang dữ liệu được yêu cầu; bộ đệm đầy phải chọn trang để đẩy ra trước khi biết yêu cầu tiếp theo.
- Dữ liệu đang đến qua mạng, không thể lưu toàn bộ; phải duy trì một thống kê hoặc mẫu đại diện trong bộ nhớ nhỏ.
- Khách hàng đến theo thời gian, phải chấp nhận/từ chối một yêu cầu hoặc cập nhật giá ngay.

**Điểm cốt lõi không phải là “chạy nhanh”**, mà là **thông tin được phép biết tại thời điểm ra quyết định**. Một chương trình xử lý từng phần tử bằng vòng for nhưng đã đọc sẵn toàn bộ đầu vào và dùng tương lai để ra quyết định thì không phải thuật toán online theo đúng mô hình.

Trong bài này, ta dùng ba ví dụ quyết định online có thể phân tích cạnh tranh—**thuê–mua**, **phân công công việc**, **thay trang cache**—và một kỹ thuật xử lý luồng—**reservoir sampling**. Mỗi ví dụ giải quyết một kiểu hạn chế thông tin khác nhau.

## 2. Online, offline và streaming khác nhau thế nào?

**Offline:** toàn bộ chuỗi yêu cầu \(\sigma=(r_1,\dots,r_T)\) được biết trước; thuật toán được nhìn sự kiện ở mọi thời điểm trước khi quyết định. Một lời giải ngoại tuyến tối ưu thường dùng làm **mốc so sánh**, chứ không phải một thứ online có thể thực thi.

**Online:** ở bước t, thuật toán biết lịch sử \(r_1,\ldots,r_t\), trạng thái đã tạo và có thể biết các tham số công khai (ví dụ giá mua B, số máy m), nhưng **không biết \(r_{t+1},r_{t+2},\ldots\)**. Quyết định có thể không thể thu hồi hoặc chỉ được đổi với chi phí.

**Streaming:** đầu vào là luồng rất dài hoặc không biết trước độ dài; giới hạn chủ yếu là **bộ nhớ, số lượt quét, thời gian xử lý mỗi phần tử**. Một thuật toán streaming thường cập nhật trạng thái sau mỗi phần tử và vì thế có tính online, nhưng không phải thuật toán streaming nào cũng tối ưu theo **competitive ratio**. Chẳng hạn reservoir sampling được đánh giá bằng phân bố xác suất mẫu, không bằng chi phí mua/thuê.

**Incremental:** cấu trúc dữ liệu thay đổi khi có sự kiện mới; có thể cập nhật đáp án cũ. Một thuật toán incremental không nhất thiết có quyết định không thể đảo ngược, nên không mặc nhiên áp cùng chứng minh online.

| Tiêu chí | Offline | Online | Streaming |
|---|---|---|---|
| Biết tương lai? | Có toàn bộ đầu vào | Không | Không, thường chỉ một hoặc vài lượt |
| Đối tượng đánh giá | Giá trị/chi phí thuật toán | Chi phí so với OPT ngoại tuyến | Sai số, bộ nhớ, update time, thông lượng |
| Quyết định có thể thu hồi? | Có thể tối ưu toàn cục | Tùy mô hình, thường hạn chế | Thường chỉ giữ trạng thái nhỏ |
| Ví dụ | Belady thay trang tối ưu | LRU, thuê–mua, list scheduling | Reservoir sampling, count-min sketch |

### 2.1. Tiền đề phải ghi rõ

Trong một bài online, hãy trả lời trước khi lập trình:

1. Sự kiện đến theo thứ tự nào? Có thể có sự kiện rỗng hoặc trùng không?
2. Thuật toán được biết những tham số gì ngay từ đầu?
3. Sau mỗi sự kiện, phải quyết định ngay hay có thể trì hoãn?
4. Được đổi quyết định cũ không? Nếu đổi thì mất phí bao nhiêu?
5. Chi phí nào cần tối thiểu, hoặc mục tiêu nào cần tối đa?
6. Đối thủ có chọn toàn bộ dãy trước khi thuật toán chạy hay được quan sát quyết định ngẫu nhiên?
7. Đầu vào có độ dài hữu hạn nhưng chưa biết, hay có thể vô hạn?
8. Nếu không thể đạt tối ưu trong mọi trường hợp, mức **bảo đảm** nào chấp nhận được?

Nếu các điều kiện này chưa rõ, “độ phức tạp” hoặc “tính tối ưu” có thể bị hiểu sai.

## 3. Phân tích cạnh tranh (*competitive analysis*)

Đối với bài toán **tối thiểu hóa**, gọi:

- \(ALG(\sigma)\): tổng chi phí thuật toán online trên chuỗi yêu cầu \(\sigma\).
- \(OPT(\sigma)\): chi phí nhỏ nhất của một thuật toán ngoại tuyến biết **toàn bộ** \(\sigma\), chịu **cùng các ràng buộc tài nguyên và luật chơi**.

Thuật toán được gọi là **c-competitive** (c≥1, với cộng hằng số) nếu tồn tại \(\beta\ge0\) không phụ thuộc vào độ dài dãy sao cho với **mọi** chuỗi hợp lệ:

**ALG(\(\sigma\)) ≤ c · OPT(\(\sigma\)) + \(\beta\).**

Khi có thể chọn \(\beta=0\), ta gọi là bảo đảm **strict** c-competitive. Với bài toán tối đa hóa, chiều so sánh phải đảo phù hợp, ví dụ ALG≥OPT/c−β; không được bê nguyên công thức cho minimization sang maximization.

### 3.1. Đây không phải xác suất thành công

Cận \(ALG≤2OPT\) nói rằng trong trường hợp xấu nhất, thuật toán tốn không quá **hai lần** chi phí tối ưu được nhìn trước. Nó **không** nói xác suất đúng là 50%, không nói sai lệch tuyệt đối hai đơn vị, và không khẳng định mỗi lần đều tệ tới hai lần.

Ví dụ nếu ALG=12 và OPT=6 thì tỷ lệ thực tế 2; nếu ALG=6 và OPT=6 thì tỷ lệ thực tế 1, mặc dù cùng dùng một thuật toán có cận 2. Khi OPT=0, tỷ số ALG/OPT không xác định: kiểm bất đẳng thức trực tiếp và xử lý trường hợp rỗng.

### 3.2. Mô hình đối thủ

- **Oblivious adversary:** chọn sẵn cả chuỗi yêu cầu mà không nhìn các lựa chọn ngẫu nhiên của thuật toán.
- **Adaptive adversary:** có thể quan sát hành vi trước đó rồi quyết định yêu cầu tiếp theo. Nếu nó còn quan sát được số ngẫu nhiên hoặc trạng thái bên trong, nhiều lập luận kỳ vọng sẽ không còn đúng.
- **Deterministic:** cùng lịch sử đầu vào và trạng thái sẽ đưa ra cùng quyết định.
- **Randomized:** dùng ngẫu nhiên nội bộ; trong mô hình chuẩn với đối thủ oblivious, cận thường được phát biểu trên \(\mathbb{E}[ALG(\sigma)]\), còn OPT là trên chuỗi \(\sigma\) đã cố định.

Không được gắn chữ “kỳ vọng” lên một cận tất định chỉ vì trong chương trình có đối tượng Random; cần định nghĩa kỳ vọng lấy theo biến ngẫu nhiên nào, và đối thủ được biết những gì.

### 3.3. Cận dưới và tính tối ưu cạnh tranh

Muốn chứng minh một thuật toán online c-competitive, ta chứng minh **cận trên** chi phí cho mọi dãy. Muốn chứng minh không thuật toán nào đạt hệ số nhỏ hơn c, cần một **cận dưới** xây đầu vào bất lợi cho mọi thuật toán trong lớp được xét. Đây là hai nhiệm vụ khác nhau.

Thường không thể có online 1-competitive vì quyết định đầu tiên giống nhau trên hai chuỗi có chung tiền tố nhưng tương lai khác nhau đòi hai lựa chọn đối lập. Chính thiếu tri thức tương lai tạo “giá của thông tin”.

## 4. Bài toán thuê–mua (*ski rental*)

Mỗi ngày cần sử dụng thiết bị ta phải chọn:

- **Thuê** với chi phí 1 cho đúng ngày hôm ấy.
- **Mua** một lần với chi phí nguyên dương \(B\), từ đó dùng miễn phí cho mọi ngày về sau.

Không biết sẽ có tổng cộng **D ngày cần sử dụng**. Ngày sử dụng tiếp theo chỉ được tiết lộ khi nó thực sự xảy ra. D có thể bằng 0 (không phát sinh nhu cầu). B được biết trước.

Một thuật toán ngoại tuyến biết D: hoặc thuê D ngày với chi phí D, hoặc mua ngay với chi phí B. Vì thế:

**OPT(D)=min(D,B).**

Không có lý do ngoại tuyến mua sau một số ngày đã thuê: mua muộn chỉ cộng thêm chi phí thuê trước đó và không rẻ hơn mua ngay.

### 4.1. Chiến lược online ngưỡng đơn giản

**Thuê tối đa B ngày; nếu sang ngày thứ B+1 vẫn cần thiết bị, mua ngay ở đầu ngày đó.** Không mua sớm chỉ vì suy đoán số ngày còn lại.

```text
onDemandDay():
    nếu đã mua:
        dùng thiết bị miễn phí
    ngược lại nếu đã thuê B ngày:
        mua hôm nay, trả B
    ngược lại:
        thuê hôm nay, trả 1
```

Sau D ngày:

- Nếu \(D≤B\): online thuê D ngày; **ALG(D)=D**.
- Nếu \(D>B\): online đã thuê B ngày, rồi mua một lần; **ALG(D)=2B**.

Do \(OPT(D)=min(D,B)\):

- Khi D≤B: ALG=OPT.
- Khi D>B: OPT=B và ALG=2B=2OPT.

Vậy chiến lược trên **strict 2-competitive**, cho mọi B≥1 và mọi D≥0. Đây là cận dễ chứng minh nhưng không phải chiến lược quyết định tốt nhất về hằng số cho mọi B nguyên: nếu mua từ ngày thứ B sau B−1 ngày thuê, có thể đạt tỷ số cực đại **2−1/B** trong mô hình rời rạc này. Hai chiến lược khác nhau một ngày; cần mô tả đúng quy tắc khi so cận.

### 4.2. Ví dụ B=5

| Số ngày thực tế D | Hành vi online | ALG | OPT | Tỷ số khi OPT>0 |
|---:|---|---:|---:|---:|
| 0 | Không có ngày nhu cầu | 0 | 0 | Không định nghĩa |
| 3 | Thuê ngày 1,2,3 | 3 | 3 | 1 |
| 5 | Thuê đủ 5 ngày | 5 | 5 | 1 |
| 6 | Thuê 5 ngày, mua ngày 6 | 10 | 5 | 2 |
| 8 | Thuê 5 ngày, mua ngày 6 | 10 | 5 | 2 |

**Không** được cho bộ giải online biết trước D để quyết định mua từ ngày 1 khi D=8. D chỉ dùng bởi bộ kiểm thử/offline oracle **sau khi chuỗi kết thúc**, còn đối tượng online phải xử lý từng lần gọi `onDemandDay`.

### 4.3. Phân tích lựa chọn giữa hai tương lai

Ở ngày đầu, hai chuỗi có cùng tiền tố “hôm nay cần dùng”:

- Nếu chỉ có một ngày D=1, thuê giá 1 là tốt; mua B (với B lớn) rất đắt.
- Nếu còn rất nhiều ngày, mua ngay B là tốt; thuê mãi có thể tốn vô hạn.

Không thể chọn tối ưu cho cả hai tương lai chỉ bằng lịch sử giống nhau. Greedy “luôn thuê” thất bại khi D lớn, và “luôn mua” thất bại khi D rất nhỏ. Ngưỡng giới hạn rủi ro của hai phía.

### 4.4. Biến thể và lưu ý

Với giá thuê r>0 và giá mua B>0, ngưỡng hợp lý phụ thuộc tỷ số B/r; cần xử lý ngày/giá rời rạc và nêu lại định lý. Không tự thay B bằng B/r rồi mặc nhiên giữ mọi chi tiết chứng minh r=1. Nếu giá thay đổi theo ngày, có phí chuyển đổi, khấu hao, hoàn tiền, hoặc mỗi ngày có nhu cầu khác nhau, mô hình thuê–mua chuẩn không còn áp dụng nguyên vẹn.

Một số tài liệu có thuật toán thuê–mua **ngẫu nhiên hóa** với tỷ số kỳ vọng tốt hơn 2 trong mô hình chuẩn và đối thủ oblivious (ở giới hạn liên tục, hằng số nổi tiếng \(e/(e-1)\)). Đây là mô hình/thuật toán khác; mã Java dưới đây minh họa chiến lược **tất định** và kiểm cận 2.

## 5. Phân công công việc đến theo luồng (*online list scheduling*)

Có m máy đồng nhất, tất cả bắt đầu rỗng. Công việc j đến với thời gian xử lý \(p_j≥0\). Khi nó đến phải gán ngay cho **một máy duy nhất**, không được chia hoặc chuyển về sau; mục tiêu là tối thiểu hóa **makespan** \(C_{\max}\): tổng tải lớn nhất trên các máy.

Thuật toán **List Scheduling / Least Loaded**:

**Khi một công việc đến, gán nó cho máy đang có tổng tải nhỏ nhất.**

```text
loads[0..m-1] = 0
onJob(p):
    chọn máy i có loads[i] nhỏ nhất
    loads[i] += p
    trả về i
makespan = max(loads)
```

Nếu nhiều máy có cùng tải, chọn máy chỉ số nhỏ nhất cho tính tái lập. Thuật toán cần biết thời lượng \(p_j\) khi job đến, **không biết các job trong tương lai**.

### 5.1. Ví dụ m=2, công việc [1,1,2]

- Job 1: gán máy 0 → tải [1,0].
- Job 2: gán máy 1 → tải [1,1].
- Job 3: hòa tải, gán máy 0 → tải [3,1].

**ALG=3**. Ngoại tuyến biết trước toàn bộ [1,1,2] có thể gán job 2 lên một máy và hai job 1 lên máy còn lại, tải [2,2], nên **OPT=2**. Tỷ số **3/2**.

Đây là ví dụ đạt cận 2−1/m khi m=2. Thuật toán online hợp lệ vẫn luôn xử lý xong tất cả job; tính “khả thi” không đồng nghĩa tối ưu makespan.

### 5.2. Chứng minh cận \((2-1/m)\)-competitive

Gọi tổng thời gian công việc là \(P=\sum_j p_j\), công việc dài nhất \(p_{\max}\). Với bất kỳ lịch hợp lệ:

- \(OPT≥P/m\), vì m máy không xử lý được tổng công việc P với makespan nhỏ hơn tải trung bình.
- \(OPT≥p_{\max}\), vì một job không được chia.

Chọn một job j kết thúc sau cùng trong lịch List Scheduling, trên máy có tải cuối cùng bằng makespan ALG. Khi j được gán, máy ấy có tải s và là máy ít tải nhất, nên:

\(s≤\text{tổng tải các job đã đến trước j}/m≤(P-p_j)/m.\)

Vậy:

\(ALG=s+p_j≤P/m+(1-1/m)p_j≤OPT+(1-1/m)OPT=(2-1/m)OPT.\)

Đây là **strict** \((2-1/m)\)-competitive, không cần cộng hằng số, và đúng với mọi thứ tự job khi m≥1. Với m=1, cả online lẫn offline có cùng makespan P nên tỷ số bằng 1.

**Bẫy chứng minh:** “job kết thúc sau cùng” không nhất thiết là job **đến cuối cùng**. Ta chọn job có thời điểm hoàn thành cuối cùng trong lịch đã tạo, rồi xét tải trước khi chính job ấy được gán. Nếu chọn job cuối trong dãy mà không xét makespan thì lập luận có thể sai.

### 5.3. Các giả thiết không được bỏ

Định lý yêu cầu máy đồng nhất, thời lượng xử lý biết khi job đến, không chia job, không có hạn chót/ưu tiên, không có thời điểm giải phóng riêng và mục tiêu là tải lớn nhất. Nếu máy có tốc độ khác nhau, job có ràng buộc phù hợp máy, có precedence, deadline hoặc được di chuyển sang máy khác, phải phân tích lại.

Với job size rất lớn, tính tổng tải trên int có thể tràn; Java trong bài dùng long và kiểm cộng an toàn. Không chọn máy theo **số job** đang giữ thay vì **tổng thời gian**: việc hai máy có cùng số job không bảo đảm tải bằng nhau.

## 6. Thay trang cache: online không thể nhìn lần truy cập kế tiếp

Bộ nhớ cache chứa tối đa k trang. Mỗi yêu cầu đòi một trang:

- Nếu trang đang trong cache: **hit**, chi phí 0.
- Nếu không: **miss/page fault**, chi phí 1, phải đưa trang vào cache.
- Nếu cache đã đầy: phải đẩy một trang ra trước khi nạp trang mới.

Vì thuật toán online không biết yêu cầu tương lai, chọn trang nào để đẩy là quyết định khó.

### 6.1. LRU (*Least Recently Used*)

LRU đẩy trang được truy cập **lâu nhất trong quá khứ** trong số các trang đang có, không dự đoán tương lai. Với cache ban đầu rỗng, k=2, chuỗi truy cập:

**[A, B, A, C, B].**

| Lượt | Trang | Hit/miss | Cache sau bước (cũ → mới) | Tổng miss |
|---:|---|---|---|---:|
| 1 | A | Miss | [A] | 1 |
| 2 | B | Miss | [A,B] | 2 |
| 3 | A | Hit | [B,A] | 2 |
| 4 | C | Miss, đẩy B | [A,C] | 3 |
| 5 | B | Miss, đẩy A | [C,B] | 4 |

**LRU có 4 miss.** Một thuật toán ngoại tuyến biết toàn bộ chuỗi (chẳng hạn chính sách Belady/Farthest-in-Future) khi C đến sẽ đẩy **A** vì biết rằng B sẽ được dùng sau còn A không; như vậy lần B cuối là hit. OPT có **3 miss**.

### 6.2. Vì sao LRU có bảo đảm cạnh tranh?

Trong mô hình paging chuẩn (chi phí miss bằng 1, cache capacity k≥1, cùng cache rỗng ban đầu), LRU là một thuật toán **conservative**: trên bất kỳ đoạn chỉ chứa không quá k trang phân biệt, nó có nhiều nhất k miss.

Phân hoạch chuỗi thành các **phase** dài nhất có không quá k trang khác nhau. Mỗi phase LRU có không quá k fault; một thuật toán ngoại tuyến cùng capacity phải phát sinh ít nhất một fault khi chuyển qua các phase thích hợp (ngoại trừ phase đầu). Suy ra một cận phổ biến, an toàn cho mọi chuỗi:

**faults_LRU(σ) ≤ k·faults_OPT(σ) + k.**

Đây là cận **cạnh tranh có cộng hằng số**. Nhiều định lý viết cận sắc hơn dưới các quy ước cache khởi tạo/phase cụ thể; không được xóa hằng số cộng nếu chưa chứng minh. Nếu k=1, LRU và OPT trùng nhau trong mô hình miss đơn vị.

### 6.3. Phân biệt LRU với Belady

Belady đẩy trang có **lần dùng tiếp theo xa nhất**; để làm vậy cần biết tương lai, nên đó là thuật toán **offline**, thường dùng làm oracle chứ không phải implementation online. Đừng viết “LRU là tối ưu” hoặc “Belady dùng được trực tiếp trong hệ thống không có future oracle”.

### 6.4. Khi nào cận paging không áp dụng?

Nếu các trang có kích thước khác nhau, miss có giá khác nhau, có preload, cache được chia tầng, hoặc có ràng buộc pin trang, cần mô hình khác. Trong thực tế cache LRU vẫn hữu dụng nhưng không còn tự động k-competitive theo định lý paging đồng kích thước/đồng chi phí.

## 7. Phân biệt online tối ưu cạnh tranh với online tối ưu tốc độ CPU

Một thuật toán online có thể mất **rất ít CPU** mỗi sự kiện nhưng chất lượng quyết định tệ (ví dụ luôn thuê thiết bị), hoặc có chi phí tính toán lớn nhưng lịch phân công tốt. **Competitive ratio** đo chi phí vận hành/giá trị mục tiêu, không đo trực tiếp độ phức tạp thời gian CPU của đoạn code.

Với các bài toán ở trên:

| Bài toán | Chi phí mục tiêu | Hiệu năng online | Thời gian cập nhật đơn giản |
|---|---|---|---|
| Ski rental | Tiền thuê + mua | ≤2·OPT | O(1) mỗi ngày |
| List scheduling m máy | Makespan lớn nhất | ≤(2−1/m)·OPT | O(m) để tìm máy ít tải |
| LRU cache capacity k | Số page fault | ≤k·OPT+k | O(1) trung bình với hash+list; cần cấu trúc phù hợp |
| Reservoir 1 phần tử | Không dùng competitive cost | Mẫu đều xác suất 1/t | O(1) bộ nhớ, O(1) update |

Giảm thời gian update của List Scheduling xuống O(log m) có thể dùng heap ưu tiên theo tải và chỉ số máy; khi ấy bất biến chọn **tải nhỏ nhất hiện tại** vẫn giữ nguyên. Nếu đổi sang chọn máy ngẫu nhiên hoặc máy có ít job nhất, chứng minh \((2-1/m)\) không áp dụng nguyên xi.

## 8. Reservoir sampling: luồng dài chưa biết độ dài

Giả sử các giá trị x₁,x₂,... đến từng cái một và ta không biết tổng số phần tử cuối cùng T. Ta muốn khi được yêu cầu dừng, giữ **một mẫu đều** trong mọi phần tử đã xuất hiện, nhưng chỉ có **O(1) bộ nhớ**.

Thuật toán **reservoir sampling kích thước 1**:

1. Khi nhận phần tử thứ t (đếm từ 1), thay mẫu hiện tại bằng phần tử mới với xác suất **1/t**.
2. Nếu không thay, giữ mẫu cũ.
3. Nếu luồng còn trống, chưa có mẫu; không trả một giá trị giả làm mẫu.

```text
seen = 0
sample = NONE
onItem(x):
    seen += 1
    nếu randomInt(seen) == 0:
        sample = x
```

### 8.1. Chứng minh mẫu đều bằng quy nạp

Tại t=1, phần tử đầu được chọn với xác suất 1. Giả sử sau t−1 phần tử, mỗi phần tử cũ có xác suất 1/(t−1) là mẫu.

Khi phần tử thứ t đến, nó được lấy với xác suất 1/t. Với một phần tử cũ i<t, xác suất còn là mẫu sau bước t:

\((1/(t-1))·(1-1/t)=1/t.\)

Vậy sau t bước mọi phần tử đã đến có xác suất **1/t**. Không cần biết trước T. Chứng minh giả định các lần gọi bộ sinh ngẫu nhiên cho phân bố đều thích hợp trên khoảng chỉ số.

### 8.2. Các giới hạn

Reservoir sampling bảo đảm **phân bố của mẫu** chứ không chứng minh một tỷ số chi phí với OPT. Mẫu một phần tử không đủ để xác định median chính xác của luồng bất kỳ. Nếu muốn ước lượng quantile, phân biệt phần tử thường gặp, hoặc đếm phần tử phân biệt với bộ nhớ nhỏ, phải dùng mô hình, cấu trúc tóm tắt và giới hạn sai số riêng.

Mã Java dùng `Random.nextInt(seen)`, vì vậy demo có giới hạn bộ đếm tối đa Integer.MAX_VALUE phần tử; bản production muốn đếm tới long cần API lấy mẫu giới hạn long đúng và xử lý overflow. `java.util.Random` phù hợp mô phỏng/kiểm thử, **không phải** nguồn ngẫu nhiên mật mã.

### 8.3. Reservoir có phải “quyết định không thể đảo” không?

Nó cập nhật mẫu theo từng phần tử mà không nhìn tương lai, nhưng **có thể thay mẫu cũ**. Điều này nhắc ta: online không nhất thiết nghĩa mọi trạng thái mãi mãi bất biến. Ta phải nêu cụ thể **quyết định nào không được rút lại** và **tài nguyên nào bị giới hạn**; trong streaming thường là bộ nhớ và số lượt đọc.

## 9. Đối thủ, randomization và tương lai bị rò rỉ

Một thuật toán dùng Random không tự làm chi phí cạnh tranh nhỏ đi. Ví dụ List Scheduling chọn máy ngẫu nhiên có thể khiến các job dài dồn vào một máy, không còn ngay cận \((2−1/m)\) của chọn tải nhỏ nhất. Muốn tuyên bố “randomized c-competitive”, cần một định lý đúng trên kỳ vọng **theo lựa chọn ngẫu nhiên**, dưới mô hình đối thủ được chỉ rõ.

**Data leakage trong kiểm thử:** nếu class OnlineRental nhận cả `totalDays` ngay từ constructor, nó có thể chọn tối ưu từ đầu nhưng đó là offline trá hình. Nếu cache replacement được gọi kèm chỉ số lần xuất hiện tương lai của mỗi trang, nó là offline. Chỉ bộ **oracle** dùng toàn bộ chuỗi để đánh giá, không truyền oracle vào đối tượng online.

**Khả năng tái lập:** seed cố định giúp tái hiện reservoir sample và test, nhưng mẫu cố định trên một seed cụ thể không chứng minh phân bố đều thống kê. Cần chứng minh toán học và kiểm PRNG API; test hữu hạn là bổ sung, không thay thế.

## 10. Cận thông tin và các biến thể

Có những bài online không thể đạt một cận cạnh tranh hữu hạn nếu không thêm giả thiết. Ví dụ chọn chấp nhận/từ chối các yêu cầu với phần thưởng khác nhau và sức chứa 1: nếu chấp nhận yêu cầu nhỏ đầu tiên, có thể bỏ lỡ phần thưởng khổng lồ sau đó; nếu từ chối, chuỗi có thể kết thúc ngay khiến online thu được 0 trong khi OPT nhận phần thưởng nhỏ. Mô hình phải nói rõ có cho phép đổi, giảm giá, hoặc có phân bố ngẫu nhiên trước hay không.

Các biến thể thường giúp thiết kế thuật toán:

- **Lookahead:** được biết trước L yêu cầu tiếp theo, giữa online và offline hoàn toàn.
- **Advice complexity:** được cấp một lượng bit thông tin về tương lai; cần tính lượng advice.
- **Recourse:** được sửa các quyết định cũ nhưng tính chi phí sửa.
- **Resource augmentation:** cho online thêm tài nguyên (ví dụ cache online lớn hơn cache offline) rồi đo competitive ratio tương ứng.
- **Stochastic/prophet setting:** biết phân bố dữ liệu hoặc cấu trúc ngẫu nhiên, khác adversarial worst case.
- **Learning-augmented online:** nhận dự đoán của mô hình học máy; đánh giá cả consistency khi dự đoán tốt và robustness khi dự đoán sai.

Mỗi biến thể cần định nghĩa đối thủ và chuẩn OPT nhất quán; không trộn lời hứa của một mô hình với lời giải trong mô hình khác.

## 11. Quy trình giải một bài “không biết tương lai”

1. **Mô tả luồng:** sự kiện xuất hiện ra sao, khi nào phải trả lời, liệu có biết T hay không?
2. **Chỉ rõ trạng thái có thể giữ:** bộ nhớ, số máy, capacity cache, ngân sách và các tham số công khai.
3. **Chỉ rõ quyết định:** thuê/mua, gán máy, đẩy trang, thay mẫu—quyết định nào là irrevocable?
4. **Đặt metric:** tiền, makespan, faults, hay sai số thống kê; không đặt ratio cho bài sampling khi không có OPT phù hợp.
5. **Dựng offline OPT** cùng luật chơi để biết mình đang so với cái gì.
6. **Đề xuất quy tắc cập nhật online** chỉ đọc lịch sử; không đưa D hay tương lai vào API.
7. **Chứng minh tính khả thi/bất biến** sau mỗi bước.
8. **Chứng minh cận**, ví dụ xét hai trường hợp D≤B/D>B, tải trung bình/longest job, hoặc phase paging.
9. **Kiểm ca biên**: chuỗi rỗng, một sự kiện, nhiều phần tử giống nhau, kết thúc ngay trước/sau ngưỡng.
10. **Kiểm thử độc lập** với oracle nhìn toàn bộ dãy trên kích thước nhỏ, nhưng không biến oracle thành thành phần ra quyết định online.
11. **Báo cáo đúng loại bảo đảm:** strict hay additive competitive, expected hay deterministic, và mô hình adversary nào.
12. **Phân tích tài nguyên tính toán** riêng với chi phí cạnh tranh và độ trễ xử lý sự kiện.



## 12. Java 17 hoàn chỉnh: bốn mô hình và bộ oracle ngoại tuyến

Lưu chương trình dưới tên `OnlineUnknownFutureDemo.java`. Mã minh họa tách rành mạch **class online nhận từng sự kiện** khỏi các hàm oracle được phép dùng toàn bộ chuỗi. Những hàm oracle chỉ dùng trong test, không được truyền dữ liệu tương lai cho thuật toán online.

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Random;

public final class OnlineUnknownFutureDemo {
    private OnlineUnknownFutureDemo() {}

    enum RentalDecision { RENT, BUY, OWN }

    static final class SkiRental {
        private final long buyCost;
        private long daysSeen = 0;
        private long rentedDays = 0;
        private long total = 0;
        private long buyDay = 0;
        private boolean owned = false;

        SkiRental(long buyCost) {
            if (buyCost < 1 || buyCost > 1_000_000_000L) {
                throw new IllegalArgumentException("buyCost must be 1..1e9");
            }
            this.buyCost = buyCost;
        }

        RentalDecision onDemandDay() {
            daysSeen++;
            if (owned) return RentalDecision.OWN;
            if (rentedDays == buyCost) {
                total = Math.addExact(total, buyCost);
                owned = true;
                buyDay = daysSeen;
                return RentalDecision.BUY;
            }
            rentedDays++;
            total++;
            return RentalDecision.RENT;
        }

        long totalCost() { return total; }
        long buyDay() { return buyDay; }
        long daysSeen() { return daysSeen; }

        static long offlineOpt(long days, long buyCost) {
            if (days < 0 || buyCost < 1) {
                throw new IllegalArgumentException("invalid horizon or price");
            }
            return Math.min(days, buyCost);
        }
    }

    // Each arriving job is assigned irrevocably to a least-loaded
    // identical machine. Ties go to lower machine index.
    static final class LeastLoaded {
        private final long[] loads;

        LeastLoaded(int machines) {
            if (machines < 1 || machines > 1000) {
                throw new IllegalArgumentException("machines must be 1..1000");
            }
            loads = new long[machines];
        }

        int onJob(long processingTime) {
            if (processingTime < 0 || processingTime > 1_000_000_000L) {
                throw new IllegalArgumentException("invalid processing time");
            }
            int best = 0;
            for (int i = 1; i < loads.length; i++) {
                if (loads[i] < loads[best]) best = i;
            }
            loads[best] = Math.addExact(loads[best], processingTime);
            return best;
        }

        long makespan() {
            long result = 0;
            for (long load : loads) {
                result = Math.max(result, load);
            }
            return result;
        }

        long[] snapshot() { return loads.clone(); }
    }

    // Offline exact oracle for tiny scheduling instances. It enumerates
    // every assignment, not using the online least-loaded rule.
    static long offlineBestSchedule(int machines, long[] jobs) {
        if (machines < 1 || machines > 3 || jobs.length > 8) {
            throw new IllegalArgumentException("oracle size exceeded");
        }
        for (long p : jobs) {
            if (p < 0) throw new IllegalArgumentException("negative job");
        }
        return exactAssignments(jobs, 0, new long[machines],
            Long.MAX_VALUE);
    }

    private static long exactAssignments(
            long[] jobs, int index, long[] load, long best) {
        if (index == jobs.length) {
            long makespan = 0;
            for (long x : load) makespan = Math.max(makespan, x);
            return Math.min(best, makespan);
        }

        // Symmetry: equivalent equal-load machines need one branch only.
        for (int machine = 0; machine < load.length; machine++) {
            boolean duplicateLoad = false;
            for (int earlier = 0; earlier < machine; earlier++) {
                if (load[earlier] == load[machine]) {
                    duplicateLoad = true;
                    break;
                }
            }
            if (duplicateLoad) continue;

            load[machine] += jobs[index];
            long partialMax = 0;
            for (long x : load) partialMax = Math.max(partialMax, x);
            if (partialMax < best) {
                best = exactAssignments(
                    jobs, index + 1, load, best);
            }
            load[machine] -= jobs[index];
        }
        return best;
    }

    // LRU paging with fixed capacity and unit fault costs.
    static final class LruCache {
        private final int capacity;
        private final LinkedHashMap<Integer, Boolean> entries =
            new LinkedHashMap<>(16, 0.75f, true);
        private int faults = 0;

        LruCache(int capacity) {
            if (capacity < 1 || capacity > 1000) {
                throw new IllegalArgumentException("invalid capacity");
            }
            this.capacity = capacity;
        }

        boolean onRequest(int page) {
            if (entries.containsKey(page)) {
                entries.get(page); // access-order moves it to MRU
                return false;
            }
            faults++;
            if (entries.size() == capacity) {
                Iterator<Integer> iterator =
                    entries.keySet().iterator();
                iterator.next();
                iterator.remove();
            }
            entries.put(page, Boolean.TRUE);
            return true;
        }

        int faults() { return faults; }
    }

    // Offline optimal paging oracle for pages 0..5, capacity <=3.
    // Each cache-state bitmask maps to the least possible fault count.
    static int offlineBestPaging(int capacity, int[] requests) {
        if (capacity < 1 || capacity > 3) {
            throw new IllegalArgumentException("oracle capacity");
        }
        Map<Integer, Integer> dp = new HashMap<>();
        dp.put(0, 0);

        for (int page : requests) {
            if (page < 0 || page >= 6) {
                throw new IllegalArgumentException("oracle page range");
            }
            int bit = 1 << page;
            Map<Integer, Integer> next = new HashMap<>();

            for (Map.Entry<Integer, Integer> e : dp.entrySet()) {
                int state = e.getKey();
                int cost = e.getValue();

                if ((state & bit) != 0) {
                    next.merge(state, cost, Math::min);
                } else if (Integer.bitCount(state) < capacity) {
                    next.merge(state | bit, cost + 1, Math::min);
                } else {
                    for (int victim = 0; victim < 6; victim++) {
                        int vbit = 1 << victim;
                        if ((state & vbit) != 0) {
                            int updated = (state & ~vbit) | bit;
                            next.merge(updated, cost + 1, Math::min);
                        }
                    }
                }
            }
            dp = next;
        }

        int optimal = Integer.MAX_VALUE;
        for (int value : dp.values()) {
            optimal = Math.min(optimal, value);
        }
        return optimal;
    }

    // One uniform random sample from the prefix seen so far.
    static final class ReservoirOne<T> {
        private final Random rng;
        private int seen = 0;
        private T sample = null;

        ReservoirOne(Random rng) {
            this.rng = Objects.requireNonNull(rng, "rng");
        }

        void offer(T item) {
            Objects.requireNonNull(item, "item");
            if (seen == Integer.MAX_VALUE) {
                throw new IllegalStateException(
                    "counter too large for nextInt(bound)"
                );
            }
            seen++;
            if (rng.nextInt(seen) == 0) {
                sample = item;
            }
        }

        int seen() { return seen; }
        T sample() { return sample; }
    }

    private static void check(boolean ok, String what) {
        if (!ok) throw new AssertionError(what);
    }

    public static void main(String[] args) {
        SkiRental shortTrip = new SkiRental(5);
        for (int day = 0; day < 3; day++) {
            shortTrip.onDemandDay();
        }
        System.out.println(
            "Rent B=5,D=3: online=" + shortTrip.totalCost()
                + ", offline=" + SkiRental.offlineOpt(3, 5)
                + ", buyDay=" + shortTrip.buyDay()
        );

        SkiRental longTrip = new SkiRental(5);
        for (int day = 0; day < 8; day++) {
            longTrip.onDemandDay();
        }
        System.out.println(
            "Rent B=5,D=8: online=" + longTrip.totalCost()
                + ", offline=" + SkiRental.offlineOpt(8, 5)
                + ", buyDay=" + longTrip.buyDay()
        );

        long[] jobs = {1, 1, 2};
        LeastLoaded machines = new LeastLoaded(2);
        for (long p : jobs) machines.onJob(p);
        System.out.println(
            "Scheduling [1,1,2]: loads="
                + Arrays.toString(machines.snapshot())
                + ", online=" + machines.makespan()
                + ", offline=" + offlineBestSchedule(2, jobs)
        );

        int[] trace = {0, 1, 0, 2, 1};
        LruCache lru = new LruCache(2);
        for (int page : trace) lru.onRequest(page);
        System.out.println(
            "LRU [0,1,0,2,1]: faults=" + lru.faults()
                + ", offline=" + offlineBestPaging(2, trace)
        );

        ReservoirOne<Integer> sample =
            new ReservoirOne<>(new Random(483L));
        ReservoirOne<Integer> sameSeed =
            new ReservoirOne<>(new Random(483L));
        for (int item = 1; item <= 6; item++) {
            sample.offer(item);
            sameSeed.offer(item);
        }
        System.out.println(
            "Reservoir: seen=" + sample.seen()
                + ", valid=" + (sample.sample() >= 1
                    && sample.sample() <= 6)
                + ", sameSeed=" +
                sample.sample().equals(sameSeed.sample())
        );

        // Every fixed finite horizon: a true online simulation.
        for (int buy = 1; buy <= 30; buy++) {
            for (int days = 0; days <= 90; days++) {
                SkiRental run = new SkiRental(buy);
                for (int t = 0; t < days; t++) {
                    run.onDemandDay();
                }
                long opt = SkiRental.offlineOpt(days, buy);
                long expected = days <= buy ? days : 2L * buy;
                check(run.totalCost() == expected,
                    "wrong rental threshold");
                check(run.totalCost() <= 2 * opt,
                    "rental bound violated");
                check(run.buyDay() == (days > buy ? buy + 1 : 0),
                    "wrong buy day");
            }
        }

        Random random = new Random(2026483L);
        for (int trial = 0; trial < 900; trial++) {
            int m = 1 + random.nextInt(3);
            int n = random.nextInt(9);
            long[] tinyJobs = new long[n];
            LeastLoaded online = new LeastLoaded(m);

            for (int j = 0; j < n; j++) {
                tinyJobs[j] = 1 + random.nextInt(9);
                online.onJob(tinyJobs[j]);
            }
            long opt = offlineBestSchedule(m, tinyJobs);
            long got = online.makespan();

            check(got >= opt, "schedule beats OPT");
            check(m * got <= (2L * m - 1) * opt,
                "scheduling competitive bound");
        }

        for (int trial = 0; trial < 1_200; trial++) {
            int capacity = 1 + random.nextInt(3);
            int n = random.nextInt(13);
            int[] requests = new int[n];
            LruCache online = new LruCache(capacity);

            for (int i = 0; i < n; i++) {
                requests[i] = random.nextInt(6);
                online.onRequest(requests[i]);
            }
            int opt = offlineBestPaging(capacity, requests);
            check(online.faults() >= opt, "LRU beats OPT");
            check(online.faults() <= capacity * opt + capacity,
                "paging bound violated");
        }

        for (int trial = 0; trial < 1_500; trial++) {
            int n = random.nextInt(51);
            long seed = random.nextLong();
            ReservoirOne<Integer> x =
                new ReservoirOne<>(new Random(seed));
            ReservoirOne<Integer> y =
                new ReservoirOne<>(new Random(seed));

            for (int i = 0; i < n; i++) {
                x.offer(i);
                y.offer(i);
            }
            check(x.seen() == n && y.seen() == n,
                "reservoir counter");
            check(Objects.equals(x.sample(), y.sample()),
                "seed reproducibility");
            check(n == 0 ? x.sample() == null
                : x.sample() >= 0 && x.sample() < n,
                "reservoir must pick from stream");
        }

        System.out.println("Ski rental exhaustive: 2730 PASS");
        System.out.println("Scheduling exact oracle: 900 PASS");
        System.out.println("Paging offline DP: 1200 PASS");
        System.out.println("Reservoir invariants: 1500 PASS");
    }
}
```

### 12.1. Biên dịch và chạy

Cài JDK 17 trở lên, lưu tệp UTF-8:

```bash
javac -encoding UTF-8 OnlineUnknownFutureDemo.java
java OnlineUnknownFutureDemo
```

**Stdout xác định:**

```text
Rent B=5,D=3: online=3, offline=3, buyDay=0
Rent B=5,D=8: online=10, offline=5, buyDay=6
Scheduling [1,1,2]: loads=[3, 1], online=3, offline=2
LRU [0,1,0,2,1]: faults=4, offline=3
Reservoir: seen=6, valid=true, sameSeed=true
Ski rental exhaustive: 2730 PASS
Scheduling exact oracle: 900 PASS
Paging offline DP: 1200 PASS
Reservoir invariants: 1500 PASS
```

### 12.2. Các bất biến của từng class

| Class/hàm | Phần đã biết khi quyết định | Bất biến/kết quả | Hạn chế |
|---|---|---|---|
| `SkiRental.onDemandDay` | B, số ngày đã đến, đã mua chưa | Chỉ mua một lần, đúng ngày B+1 nếu vẫn cần | B trong 1..1e9 |
| `SkiRental.offlineOpt` | **D đầy đủ** | min(D,B) | Chỉ oracle, không gọi từ `onDemandDay` |
| `LeastLoaded.onJob` | Tải hiện tại, kích thước job mới | Gán ngay máy ít tải nhất | m trong 1..1000, job≥0 |
| `offlineBestSchedule` | **Toàn bộ job** | Vét cạn phương án gán, lấy makespan nhỏ nhất | m≤3, n≤8; chỉ oracle |
| `LruCache.onRequest` | Cache hiện tại, lịch sử hit/miss | Evict LRU; capacity được giữ | k trong 1..1000 |
| `offlineBestPaging` | **Toàn bộ trace** | DP mọi trạng thái cache; minimum faults | k≤3; page IDs 0..5 |
| `ReservoirOne.offer` | Mẫu, số phần tử đã thấy, item mới | Mỗi prefix có một mẫu, xác suất lý tưởng 1/t | count int, PRNG demo |

**Ski rental:** Khi đã mua, các sự kiện sau vẫn tăng bộ đếm ngày nhưng không tăng chi phí. Trường `buyDay=0` là “chưa mua”, không phải “mua ngày 0”. Với D=B, thuật toán chưa mua. Với D>B, mua đúng ngày B+1, chi phí tối đa 2B.

**Scheduling:** `LeastLoaded` quét m máy để chọn tải nhỏ nhất, có quy tắc tie-break là chỉ số nhỏ nhất. `offlineBestSchedule` dùng vét cạn với tối ưu đối xứng: máy có cùng tải là các nhánh tương đương. Điều này thay đổi thứ tự duyệt nhưng không thay đổi tối ưu. Bộ test dùng phép so sánh **nguyên** `m*ALG <= (2*m−1)*OPT`, không phụ thuộc rounding double.

**LRU:** `LinkedHashMap` với `accessOrder=true` chuyển mục đã truy cập tới MRU. Trên miss và cache đầy, iterator ở đầu khóa cho trang LRU. DP ngoại tuyến mã hóa tập trang hiện có dưới bitmask; mỗi trạng thái giữ **ít fault nhất**. Nó thử mọi nạn nhân trên cache full, nên là oracle tốt cho trace ngắn. Việc chỉ lưu tập trang trong oracle là đủ vì tối ưu ngoại tuyến được phép lựa chọn eviction theo cả tương lai; trong mô hình miss chi phí đơn vị, thứ tự truy cập quá khứ không ảnh hưởng tính khả thi của các phương án thay trang trong tương lai.

**Reservoir:** Mỗi lần gọi `offer` chỉ nhìn item hiện tại và bộ đếm, không biết chiều dài luồng. Hai instance dùng cùng seed trên cùng chuỗi ra cùng mẫu—đó là kiểm **tái lập**, không chứng minh mẫu đã phân bố đều trong một lần chạy. Phân bố đều được chứng minh bằng quy nạp ở mục 8.

### 12.3. Kiểm thử chống những cách “offline trá hình”

- Chạy thuê–mua cho B=1..30 và D=0..90: **30×91=2.730** trường hợp. Mỗi instance tạo đối tượng online mới, gọi `onDemandDay` đúng D lần, rồi **sau cùng** mới lấy OPT từ D để kiểm.
- Chạy **900** lịch job có m=1..3, n=0..8; online gán job ngay khi xuất hiện, ngoại tuyến brute-force kiểm mệnh đề \(m·ALG≤(2m−1)·OPT\) với cùng số máy và job.
- Chạy **1.200** trace cache có k=1..3 và 0..12 yêu cầu trang 0..5; LRU không dùng future, oracle DP đọc toàn bộ trace, kiểm `OPT≤faults_LRU≤k*OPT+k`.
- Chạy **1.500** luồng có 0..50 item; kiểm counter, phần tử mẫu xuất phát từ luồng và khả năng tái hiện cùng seed. Test không khẳng định mọi mẫu đều có tần suất bằng nhau ở một số lần thử hữu hạn.

**Giới hạn chương trình:** đây là bản trình diễn sư phạm; bộ giải exact ngoại tuyến cố ý giới hạn input nhỏ. Không đem brute force lên chuỗi thực tế dài rồi kỳ vọng vẫn nhanh. Các định lý online không phụ thuộc việc có thể tính OPT nhanh hay không.

## 13. Chứng minh tính đúng khác bảo đảm cạnh tranh

### 13.1. Ski rental

**Khả thi:** Mỗi ngày có nhu cầu được đáp ứng bằng thuê, mua hoặc dùng đồ đã mua. Không trả tiền mua hai lần; không dùng thiết bị trước khi có quyền sử dụng. **Bảo đảm:** chi phí tối đa 2 min(D,B), chứng minh bằng hai trường hợp D≤B và D>B.

### 13.2. Least-loaded scheduling

**Khả thi:** Mỗi job gán đúng một máy, không chia, tổng tải được cập nhật chính xác. **Bảo đảm:** makespan ≤(2−1/m)OPT nhờ tải trung bình và job dài nhất. Một lịch khả thi với makespan lớn hơn OPT không phải sai logic; đó là bản chất thiếu future.

### 13.3. Cache LRU

**Khả thi:** Sau mỗi yêu cầu, trang vừa gọi ở cache; số trang không vượt capacity. **Bảo đảm cạnh tranh:** số miss không vượt kOPT+k theo mô hình paging chuẩn. Trên một trace cụ thể, LRU có thể trùng OPT hoặc tệ hơn; không khẳng định LRU luôn chọn eviction đúng như Belady.

### 13.4. Reservoir

**Khả thi:** Khi đã thấy t≥1 item, mẫu thuộc một item đã thấy. **Bảo đảm:** với nguồn ngẫu nhiên đều lý tưởng, mỗi vị trí có xác suất 1/t là mẫu. Đây là tính đúng phân bố chứ **không phải** cạnh tranh theo offline cost.

## 14. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Cho online đọc toàn bộ D, jobs hoặc trace | Vi phạm mô hình chưa biết tương lai | API nhận từng sự kiện, oracle tách riêng |
| Xem chi phí competitive như thời gian CPU | Hai metric khác nhau | Báo giá vận hành và update complexity riêng |
| Lấy tỷ số khi OPT=0 | 0/0 không xác định | Dùng bất đẳng thức trực tiếp, xử lý rỗng |
| “2-competitive” nghĩa xác suất 50% | Nhầm tỷ lệ chi phí với xác suất | Đọc ALG≤2OPT+β |
| Không nói có cộng β | Có thể phát biểu cận sai | Nêu strict hay additive |
| So với oracle có nhiều tài nguyên hơn | So sánh không công bằng | Cùng capacity, máy, luật chơi |
| Ski rental mua trước khi biết ngày tiếp theo còn dùng | Làm lộ tương lai | Mua chỉ khi ngày B+1 **thực sự đến** |
| B=5 nhưng mua ở ngày 5 trong chiến lược “thuê B ngày” | Lẫn thời điểm ngưỡng | Sau B ngày thuê, mua ngày B+1 |
| Tuyên bố mọi phương pháp ski rental đều có tỷ lệ đúng 2 | Các threshold khác nhau | Chứng minh trên **quy tắc cụ thể** |
| Chọn máy theo số job | Khác chọn theo tổng tải | Chọn máy có tổng thời gian nhỏ nhất |
| Quên m=1 hoặc n=0 | Kết quả/ratio dễ sai | OPT=ALG hợp lệ, xử lý rỗng |
| Nói job cuối **đến** nhất định hoàn thành cuối cùng | Lẫn thứ tự với makespan | Chọn job làm nên makespan |
| Không giới hạn long overflow khi cộng tải | Tải có thể âm do tràn | Math.addExact hoặc chứng minh bound |
| LRU evict MRU | Đảo chiều chính sách | Đẩy trang lâu không dùng nhất |
| LRU dùng “lần dùng tiếp theo” | Đây là thuật toán offline | Dùng lịch sử cho LRU, future cho oracle |
| Nói LRU tối ưu mọi chuỗi | Có ví dụ 4 miss so với 3 | Kiểm với DP/Belady offline |
| Bỏ hệ số k hoặc +k khỏi cận paging | Mất điều kiện định lý | Nêu đầy đủ ≤kOPT+k |
| Reservoir thay mẫu với xác suất cố định | Không còn đều theo prefix | Xác suất thay phải là 1/t |
| Sử dụng Random.nextInt(0) cho luồng rỗng | API lỗi bound không dương | Chỉ gọi sau khi tăng count |
| Dùng Random với seed cố định như chứng nhận thống kê | Một lần chạy không chứng minh phân bố | Chứng minh quy nạp 1/t |
| Cho rằng thuật toán streaming nào cũng cần competitive ratio | Sai metric | Đánh giá sai số, bộ nhớ, throughput |
| Trộn đối thủ oblivious và adaptive | Cận kỳ vọng không nhất thiết giữ | Xác định adversary |
| Đánh đồng lookahead/recourse với online không thông tin | Điều kiện đã thay đổi | Ghi rõ khả năng nhìn trước và đổi quyết định |
| Đọc dữ liệu tương lai ở bài test rồi dùng trong code online | Che lỗi mô hình | Chỉ dùng future trong kiểm thử offline |

## 15. Bài tập có đáp án

**Bài 1.** Thuật toán online khác offline thế nào? *Đáp án:* online phải quyết định từ lịch sử, không có toàn bộ tương lai.

**Bài 2.** Một chương trình đọc hết input rồi xử lý bằng for có tự là online không? *Đáp án:* không nếu nó dùng dữ liệu tương lai để quyết định.

**Bài 3.** Competitive ratio cho bài minimization với cộng hằng là gì? *Đáp án:* ALG(σ)≤cOPT(σ)+β cho mọi σ.

**Bài 4.** 2-competitive là xác suất đúng 50% không? *Đáp án:* không; là cận tỷ lệ chi phí.

**Bài 5.** Offline OPT của ski rental giá thuê 1, giá mua B, horizon D? *Đáp án:* min(D,B).

**Bài 6.** Với B=5,D=3, online ngưỡng “thuê B ngày” tốn bao nhiêu? *Đáp án:* 3.

**Bài 7.** Với B=5,D=8, online mua ngày nào và chi phí bao nhiêu? *Đáp án:* ngày 6, tổng chi phí 10.

**Bài 8.** Với B=5,D=5, chiến lược đó đã mua chưa? *Đáp án:* chưa, chỉ thuê 5 ngày.

**Bài 9.** Vì sao thuật toán thuê–mua ngưỡng B là 2-competitive? *Đáp án:* D≤B có ALG=OPT; D>B có ALG=2B=2OPT.

**Bài 10.** Khi D=0, chi phí và tỷ số ALG/OPT thế nào? *Đáp án:* cả hai chi phí 0, tỷ số 0/0 không định nghĩa.

**Bài 11.** List scheduling đặt job vào đâu? *Đáp án:* máy có tổng tải nhỏ nhất hiện tại.

**Bài 12.** Với m=2, jobs [1,1,2], tải cuối? *Đáp án:* [3,1] khi hòa chọn máy chỉ số nhỏ.

**Bài 13.** Offline makespan tối ưu cho [1,1,2], m=2? *Đáp án:* 2.

**Bài 14.** Hệ số cạnh tranh của List Scheduling trên m máy đồng nhất? *Đáp án:* 2−1/m.

**Bài 15.** Hai cận dưới cho OPT trong bài job scheduling? *Đáp án:* P/m và p_max.

**Bài 16.** Vì sao không chọn “job đến cuối cùng” trong chứng minh? *Đáp án:* job tạo makespan có thể đến trước nhưng hoàn thành muộn hơn.

**Bài 17.** Cache LRU đẩy trang nào? *Đáp án:* trang ít được truy cập gần đây nhất.

**Bài 18.** Với k=2, trace [A,B,A,C,B] LRU bao nhiêu miss? *Đáp án:* 4.

**Bài 19.** Offline tối ưu trace ấy bao nhiêu miss? *Đáp án:* 3.

**Bài 20.** Belady dùng thông tin gì mà LRU không có? *Đáp án:* lần truy cập tiếp theo trong tương lai.

**Bài 21.** Một cận cạnh tranh an toàn cho LRU cache k là gì? *Đáp án:* faults_LRU≤k·OPT+k trong mô hình chuẩn.

**Bài 22.** Mục tiêu reservoir sampling là gì? *Đáp án:* mẫu đều trong mọi phần tử của prefix đã thấy với bộ nhớ hằng.

**Bài 23.** Phần tử thứ t được chọn làm mẫu với xác suất nào? *Đáp án:* 1/t.

**Bài 24.** Một phần tử cũ còn được chọn sau t bước với xác suất gì? *Đáp án:* (1/(t−1))·(1−1/t)=1/t.

**Bài 25.** Reservoir có cần biết tổng chiều dài T không? *Đáp án:* không.

**Bài 26.** Reservoir có bảo đảm competitive ratio cho chi phí mua/thuê không? *Đáp án:* không; nó có bảo đảm phân bố mẫu.

**Bài 27.** Oblivious adversary khác adaptive adversary? *Đáp án:* oblivious chọn trước cả dãy; adaptive có thể phụ thuộc diễn biến đã quan sát.

**Bài 28.** Thuật toán Random có mặc nhiên tốt hơn trước adaptive adversary? *Đáp án:* không, cần phân tích theo mô hình đối thủ.

**Bài 29.** Nếu cho online nhìn trước 3 yêu cầu, đây vẫn là cùng mô hình không lookahead không? *Đáp án:* không, đã thêm thông tin.

**Bài 30.** Nếu cho chuyển job giữa các máy với chi phí 0, chứng minh ban đầu còn áp dụng nguyên vẹn không? *Đáp án:* mô hình đã thay đổi; phải phân tích lại.

**Bài 31.** Tại sao không dùng toàn bộ trace trong LRU.onRequest? *Đáp án:* vì đó là lộ dữ liệu tương lai, biến online thành offline.

**Bài 32.** Với m=1, cận 2−1/m bằng bao nhiêu? *Đáp án:* 1 và online luôn trùng OPT.

**Bài 33.** Mục đích của oracle offline trong kiểm thử online? *Đáp án:* biết giá trị tối ưu sau khi có đủ dữ liệu để kiểm tỷ số, không tham gia quyết định online.

**Bài 34.** Khi nào không thể nói thuật toán đạt c-competitive? *Đáp án:* khi chưa định nghĩa đúng metric, OPT, adversary và chưa chứng minh cận mọi chuỗi hợp lệ.

## 16. Checklist trước khi triển khai

1. Xác định sự kiện nào đến một lần, thời điểm nào buộc phải quyết định.
2. Viết rõ tham số được phép biết ban đầu và thông tin **không** được biết.
3. Chỉ ra quyết định irrevocable/recourse và chi phí sửa quyết định.
4. Xác định metric: tiền, makespan, faults, sai số thống kê hay thông lượng.
5. Xác định OPT ngoại tuyến với **cùng** luật chơi và tài nguyên.
6. Với minimization, phát biểu đúng ALG≤cOPT+β; nêu rõ β.
7. Nếu là randomized, xác định kỳ vọng và loại adversary.
8. Thuê–mua: không mua trước khi có nhu cầu ngày B+1; xử lý D=0, B=1.
9. List scheduling: chọn **tải** nhỏ nhất, không phải ít công việc nhất; xét m=1 và job 0.
10. Cache: giữ capacity, trên hit cập nhật recency, trên miss eviction đúng LRU.
11. Không nhầm Belady dùng future với LRU dùng lịch sử.
12. Streaming: giới hạn bộ nhớ, số lượt đọc và cập nhật mỗi phần tử.
13. Reservoir: xác suất chọn item thứ t là 1/t; xử lý luồng rỗng và count overflow.
14. Kiểm số học tràn, chi phí âm/không hợp lệ và nhu cầu bất thường.
15. Xây test có oracle offline **tách API online**, gồm case nhỏ vét cạn/DP.
16. Phân biệt cận chứng minh cho mọi dãy với số liệu trung bình thực nghiệm.
17. Không chuyển bảo đảm của mô hình chuẩn sang biến thể có máy khác tốc độ, page size khác nhau hoặc recourse.
18. Báo rõ latency cập nhật, bộ nhớ và chi phí cạnh tranh như ba thước đo riêng.

## Kết luận

**Thuật toán trực tuyến** phải ra quyết định từ lịch sử khi tương lai chưa có. **Phân tích cạnh tranh** đặt chi phí của nó cạnh lời giải ngoại tuyến biết trước toàn bộ dãy, cùng luật chơi và tài nguyên. Thuê–mua ngưỡng B có cận **2-competitive**; phân công job vào máy ít tải nhất có cận **2−1/m**; LRU cache có một cận đơn giản **k·OPT+k**. Những con số này là cận chi phí, không phải xác suất thành công.

**Thuật toán xử lý luồng** như reservoir sampling cũng hoạt động khi chưa biết dữ liệu tương lai, nhưng bảo đảm của nó có thể là **đúng phân bố mẫu** và **bộ nhớ O(1)** thay vì competitive ratio. Điều quan trọng nhất là hiểu **cái gì được biết khi quyết định**, **cái gì cần tối ưu** và **cận nào đã được chứng minh**. Không đưa tương lai vào API online, và chỉ dùng oracle offline để kiểm thử sau khi chuỗi kết thúc.
