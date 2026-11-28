# Vì sao Bloom filter chuẩn không hỗ trợ xóa tùy ý

Trong nhiều hệ thống, **Bloom filter** được dùng để trả lời nhanh: “Khóa X có thể thuộc tập đã ghi nhận không?”. Một bộ lọc nhỏ có thể thay thế rất nhiều lượt đọc đĩa hoặc truy vấn mạng không cần thiết. Nhưng khi dữ liệu thay đổi, một câu hỏi mới xuất hiện:

> **Nếu một khóa không còn thuộc tập, liệu ta có thể xóa nó khỏi Bloom filter bằng cách tắt các bit mà khóa ấy đã bật hay không?**

Câu trả lời đối với **Bloom filter chuẩn chỉ dùng bit** là **không thể xóa một khóa tùy ý một cách an toàn**. Vấn đề không nằm ở việc thiếu một lệnh xóa trong mã nguồn. Nó xuất phát từ **thông tin đã mất**: nhiều khóa có thể bật chung một bit, trong khi bộ lọc chỉ ghi bit là **0 hoặc 1**, không ghi khóa nào đã bật bit đó hoặc có bao nhiêu khóa đang cần đến nó.

Nếu giữ nguyên bit của khóa đã xóa, bộ lọc có thể tiếp tục trả **“có thể có”** cho khóa ấy, dù nguồn dữ liệu chính xác đã xóa. Nếu tự tắt bit, có thể làm một khóa **vẫn còn tồn tại** bị trả **“không có”** — tức tạo **âm tính giả**, phá hỏng bảo đảm quan trọng nhất của Bloom filter chỉ-thêm.

Bài thuộc chương **Cấu trúc xác suất** trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, tập trung học cấu trúc dữ liệu thông qua **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để lựa chọn cấu trúc phù hợp. Bài này giải thích nguyên nhân về mặt thông tin, ví dụ cụ thể, cách các biến thể như **counting Bloom filter** hỗ trợ xóa có điều kiện, và cách thiết kế an toàn khi dữ liệu cần hết hạn hoặc bị loại bỏ.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Nhắc lại cấu trúc Bloom chuẩn gồm **m bit, h vị trí băm** và hợp đồng của add/might_contain.
2. Phân biệt **“đã từng được thêm”** với **“hiện vẫn thuộc tập có hiệu lực”**.
3. Chứng minh tại sao bit chỉ-thêm **0→1** tạo bảo đảm **không âm tính giả** cho các khóa đã add thành công.
4. Truy vết phản ví dụ: **xóa bit của A làm B bị âm tính giả** vì A và B cùng cần một bit.
5. Giải thích trường hợp **hai khóa có cùng toàn bộ dấu vết băm**: không thể bắt một khóa trả False mà vẫn giữ khóa kia True chỉ từ bit array.
6. Phân biệt **dương tính giả sau khi dữ liệu đã bị xóa** với lỗi âm tính giả do sửa bit không an toàn.
7. Hiểu vì sao **add trùng khóa**, không có bộ đếm sở hữu bit và va chạm khiến thao tác delete mơ hồ.
8. Mô tả cấu tạo **counting Bloom filter**, bất biến các bộ đếm và điều kiện xóa hợp lệ.
9. Phân tích rủi ro xóa khóa **chưa từng được thêm nhưng query trả True**, tràn/giảm âm bộ đếm, và cập nhật đồng thời.
10. Viết Python minh họa lỗi tắt bit, một counting Bloom có kiểm tra khóa hiện hữu, và trường hợp xóa nhầm làm hỏng bộ đếm.
11. So sánh thời gian/bộ nhớ của Bloom bit chuẩn, counting Bloom, set chính xác và các thiết kế theo snapshot/phân vùng thời gian.
12. Chọn cách **tái xây, bỏ phân vùng, dùng nguồn xác minh chính xác, hoặc cấu trúc hỗ trợ xóa khác** theo yêu cầu.
13. Nhận diện lỗi nhất quán với database, khôi phục snapshot, tái chèn sau xóa và truy vấn đồng thời.
14. Thiết kế các kiểm thử để đảm bảo không âm tính giả đối với **tập khóa hiện còn hiệu lực**.
15. Giải được các bài tập phản ví dụ, định nghĩa bất biến và lựa chọn phương án xóa.

## 2. Trước khi xóa: Bloom filter đang biểu diễn tập nào?

Giả sử tập có thẩm quyền trong database là **S_active**: những khóa hiện đang tồn tại. Bloom filter chuẩn có một mảng **m bit** và **h vị trí băm** cho mỗi khóa. Nếu khóa x được add thành công, tất cả bit tại các vị trí:

\[
H_0(x),H_1(x),\ldots,H_{h-1}(x)
\]

được bật thành 1.

Khi hỏi **might_contain(x)**:

- Nếu **ít nhất một vị trí** của x bằng 0, trả **False**.
- Nếu **tất cả các vị trí** của x bằng 1, trả **True**.

True có nghĩa **“có thể có”**, không phải bằng chứng x thuộc tập. Các khóa khác có thể đã bật đủ những bit tương ứng với x.

### 2.1. Hai cách hiểu membership khác nhau

**Đã từng được thêm (ever inserted).** Bloom chỉ-thêm không quên những dấu vết cũ. Nếu một khóa từng được add, filter luôn trả True về khóa đó, miễn không có lỗi bit/hàm băm.

**Đang có hiệu lực (currently active).** Database có thể xóa hoặc làm hết hạn một khóa. Bloom bit chuẩn **không tự cập nhật ngược** cho phép xóa ấy. Khi đó một khóa đã bị xóa khỏi S_active vẫn có thể nhận True từ filter.

~~~text
Database trước xóa:   {A, B}
Bloom sau add(A,B):   mảng bit biểu diễn dấu vết A và B

Database sau DELETE(A): {B}
Bloom không đổi:        dấu vết của A vẫn còn
~~~

Nếu câu hỏi nghiệp vụ là **“A đã từng xuất hiện chưa?”**, giữ dấu vết A có thể hoàn toàn phù hợp. Nếu câu hỏi là **“A hiện có trong database không?”**, kết quả True cho A phải được **xác minh**; nó không còn tương ứng với một true positive theo tập hiện hành.

### 2.2. Bốn loại kết quả so với tập có hiệu lực

| Sự thật trong S_active | Filter True (“có thể có”) | Filter False (“không có”) |
| --- | --- | --- |
| x đang tồn tại | True positive (TP) | **False negative (FN)** |
| x không còn/không tồn tại | **False positive (FP)** | True negative (TN) |

Bộ lọc **chỉ-thêm và không reset bit** vẫn bảo đảm không FN cho **các khóa đang hoạt động đã được add thành công**, vì tất cả bit của chúng còn nguyên. Nhưng số khóa đã hết hạn/từng tồn tại có thể làm **FP tính theo S_active tăng**.

Điều quan trọng là xác định **tập tham chiếu**. FPR đối với tập **đã từng thêm** và FPR đối với tập **đang còn hiệu lực** có thể khác nhau, vì trong tập thứ hai có các khóa từng được thêm nhưng nay đã xóa.

### 2.3. Những điều Bloom chuẩn không lưu

Một bit chỉ cho biết **“ít nhất một lần đã được bật”**, không cho biết:

- Bit ấy được **khóa nào** bật.
- Có **bao nhiêu khóa phân biệt** hiện cần bit ấy.
- Một khóa đã được add **bao nhiêu lần**.
- Có bao nhiêu khóa dùng **đúng cùng toàn bộ vị trí băm**.
- Bit có phải được bật bởi một khóa **đã hết hạn** hay không.

Những thông tin này có thể cần thiết để gỡ một dấu vết mà vẫn giữ mọi dấu vết của các khóa khác.

## 3. Vì sao thao tác chỉ-thêm giữ được bất biến?

Bloom bit chuẩn có hai thao tác cơ bản:

~~~text
ADD(x):
    for j in H_0(x), ..., H_(h-1)(x):
        bits[j] = 1

MIGHT_CONTAIN(x):
    for j in H_0(x), ..., H_(h-1)(x):
        if bits[j] == 0:
            return False
    return True
~~~

Sau add(x) thành công, mọi bit của x đều là 1. Các lần add khác **chỉ có thể bật thêm**, không tắt bit đã bật.

Gọi \(B_t[j]\) là bit ở vị trí j sau t lần add hợp lệ. Bất biến:

\[
B_{t+1}[j]\ge B_t[j],\qquad B_t[j]\in\{0,1\}.
\]

Nếu x đã được add ở thời điểm t:

\[
B_t[H_i(x)]=1\quad\text{với mọi }i.
\]

Vì các bit không giảm, ở mọi thời điểm sau đó:

\[
\boxed{x\in S_{\rm inserted}\Longrightarrow
\mathrm{mightContain}(x)=\mathrm{True}.}
\]

Suy ra bằng phản đảo:

\[
\boxed{\mathrm{mightContain}(x)=\mathrm{False}
\Longrightarrow x\notin S_{\rm inserted}.}
\]

Đây là **bảo đảm chính xác một phía**, không phụ thuộc FPR mục tiêu là 0,1% hay 10%. Nó yêu cầu các thao tác add đã hoàn tất, hash/encoding không đổi, trạng thái không bị mất và bit không bị tắt.

**Xóa một bit đang bằng 1 là bước phá tính đơn điệu**. Nếu bit ấy cũng nằm trong bộ vị trí băm của một khóa khác, ta có thể mất kết luận trên.

## 4. Phản ví dụ tối thiểu: xóa A khiến B thành âm tính giả

Giả sử m=8 bit, h=2 và các vị trí băm được cho sẵn:

| Khóa | Vị trí băm |
| --- | --- |
| A | {1,4} |
| B | {4,6} |
| C | {1,6} |

Ban đầu:

~~~text
index: 0 1 2 3 4 5 6 7
bits:  0 0 0 0 0 0 0 0
~~~

Add A:

~~~text
H(A)={1,4}

index: 0 1 2 3 4 5 6 7
bits:  0 1 0 0 1 0 0 0
~~~

Add B:

~~~text
H(B)={4,6}

index: 0 1 2 3 4 5 6 7
bits:  0 1 0 0 1 0 1 0
~~~

Ở thời điểm này:

~~~text
might_contain(A) = True   (bit 1,4 đều 1)
might_contain(B) = True   (bit 4,6 đều 1)
might_contain(C) = True   (bit 1,6 đều 1: FP vì C chưa add)
~~~

Bây giờ muốn **DELETE(A)** nhưng vẫn giữ B. Một cách làm ngây thơ là **tắt tất cả bit của A**:

~~~text
DELETE_NAIVE(A):
    bits[1] = 0
    bits[4] = 0

Sau xóa:
index: 0 1 2 3 4 5 6 7
bits:  0 0 0 0 0 0 1 0
~~~

Khi query B:

~~~text
H(B)={4,6}
bit[4]=0, bit[6]=1

might_contain(B) = False
~~~

**B chưa bị xóa khỏi tập, nhưng filter lại trả False cho B.** Đây chính là **false negative**, do bit 4 là bit **dùng chung** cho A và B.

### 4.1. Phép xóa gặp hai lựa chọn đều có nhược điểm

- **Không tắt bit:** A vẫn có thể trả True dù đã bị xóa. Nếu so với tập đang hoạt động, đây là một **dương tính giả sau xóa**; không làm B âm tính giả.
- **Tắt mọi bit của A:** Có thể làm B và các khóa khác bị **âm tính giả**, phá bảo đảm một phía.

Vấn đề không được giải quyết chỉ bằng cách sửa câu điều kiện của might_contain. Nó là vấn đề **thiếu thông tin về số khóa đang cần mỗi bit**.

### 4.2. Có thể chỉ tắt bit 1 của A trong ví dụ trên không?

Ở chính ví dụ này, nếu biết chắc **bit 1 chỉ do A cần**, tắt riêng bit 1 có thể khiến A trả False và B vẫn True. Nhưng Bloom bit chuẩn **không lưu thông tin sở hữu** để biết bit nào an toàn; muốn biết cần dữ liệu bổ sung hoặc một nguồn danh tính khóa có thẩm quyền.

Hơn nữa, có những trường hợp **không tồn tại bit riêng để tắt** — xem mục tiếp theo. Vì vậy khả năng tắt đúng một bit trong **một tình huống cụ thể** không tạo ra một thao tác **delete tổng quát** cho Bloom chuẩn.

## 5. Trường hợp mạnh hơn: hai khóa có cùng toàn bộ dấu vết

Giả sử hai khóa khác nhau A và D có đúng cùng vị trí băm:

~~~text
H(A)={1,4}
H(D)={1,4}

Sau add(A), add(D):

bit[1]=1; bit[4]=1.
~~~

Giờ cần xóa A nhưng D vẫn hoạt động.

- Nếu giữ **cả bit 1 và 4**, filter sẽ tiếp tục trả True cho A. Đây là **kết quả được phép của một bộ lọc xấp xỉ**, nhưng không có cách khẳng định A đã biến mất qua query.
- Nếu tắt **bit 1 hoặc bit 4**, query D sẽ trả False, trở thành âm tính giả.

Vì bộ vị trí băm của A và D **giống hệt nhau**, không có cách đặt hai bit để **A trả False nhưng D vẫn trả True** với kiểu truy vấn Bloom chuẩn. Ngay cả khi biết danh tính các khóa từ bên ngoài, **chỉ riêng biểu diễn bit và câu trả lời membership ấy không đủ để phân biệt chúng**.

### 5.1. Điều không thể và điều vẫn có thể

**Không thể bảo đảm bằng thao tác xóa bit tổng quát** rằng:

1. Mọi khóa còn hoạt động vẫn trả True; **và**
2. Mọi khóa đã xóa phải trả False ngay lập tức;

trong tất cả các tình huống va chạm khi chỉ có mảng bit Bloom chuẩn.

Đây **không phải** phát biểu rằng “không thể dùng một cấu trúc liên quan đến Bloom để hỗ trợ xóa”. Ta có thể **bổ sung thông tin** (bộ đếm, tập khóa chính xác, version, partition) và chấp nhận rằng **khóa đã xóa vẫn có thể là FP** sau thao tác. Điều không thể là kỳ vọng bộ lọc bit chuẩn tự khôi phục thông tin nó chưa từng lưu.

### 5.2. Phân biệt “xóa an toàn” và “đảm bảo khóa xóa luôn False”

Một cấu trúc membership xấp xỉ hỗ trợ xóa thường được coi là xóa **an toàn** nếu, sau thao tác hợp lệ:

- Mọi khóa **còn hoạt động** vẫn không bị âm tính giả.
- Khóa đã xóa **có thể** vẫn nhận True vì va chạm với các khóa còn hoạt động; mức FP này được chấp nhận và phải đo.

Nếu yêu cầu **khóa đã xóa luôn trả False với độ chính xác tuyệt đối**, phải dùng **nguồn chính xác** hoặc một hợp đồng khác, không chỉ Bloom/Counting Bloom.

## 6. Vì sao thiếu số lần sử dụng bit làm delete mơ hồ?

Hãy tưởng tượng một bit j được bật bởi nhiều khóa:

~~~text
A cần bit j.
B cần bit j.
E cần bit j.

Bloom chỉ lưu:
bit[j] = 1.
~~~

Cùng một trạng thái bit[j]=1 có thể tương ứng:

~~~text
Có 1 khóa đang cần bit j.
Có 2 khóa đang cần bit j.
Có 1000 khóa đang cần bit j.
Hoặc không còn khóa nào hiện cần, nhưng bit chưa được dọn.
~~~

Từ **giá trị 1**, không thể biết khi xóa A có nên để bit 1 hay tắt bit.

Một bộ đếm tham chiếu sẽ trả lời **bao nhiêu lần đóng góp còn tồn tại tại vị trí j**. Bloom bit chuẩn không có bộ đếm ấy; nó đã đánh đổi thông tin để tiết kiệm bộ nhớ.

### 6.1. Thêm cùng một khóa nhiều lần

~~~text
ADD(A)
ADD(A)
ADD(A)
~~~

Trạng thái bit sau ba lần thường giống sau một lần, vì cùng khóa dùng cùng vị trí băm. Vì vậy Bloom chuẩn **không phân biệt**:

- A được thêm đúng một lần;
- A được thêm ba lần;
- A đang hoạt động dưới ba tham chiếu khác nhau.

Nếu API cần **xóa từng lần xuất hiện** thay vì xóa hẳn một khóa khỏi set, còn phải lưu **ngữ nghĩa số lần add/delete** ở bên ngoài hoặc trong biến thể cấu trúc.

### 6.2. Hai loại thông tin thiếu nhau

- **Số đóng góp ở mỗi vị trí**: cần để giảm bộ đếm một cách an toàn khi xóa.
- **Khóa nào thực sự còn hoạt động**: cần để biết một lời gọi delete(x) có **hợp lệ** hay không.

Một counting Bloom filter bổ sung loại thông tin thứ nhất, nhưng **không tự biết chắc loại thứ hai**; đây là một điểm cực kỳ quan trọng khi triển khai delete.


## 7. Nếu không xóa bit, hệ thống có còn dùng Bloom được không?

**Có, nếu chấp nhận dương tính giả và định nghĩa đúng tập tham chiếu.** Một bộ lọc chỉ-thêm có thể tiếp tục hoạt động sau khi database xóa khóa: giữ nguyên các bit **không làm mất dấu vết của khóa còn hoạt động**, vì thế không tự gây âm tính giả.

Tuy nhiên, có hai câu hỏi khác nhau:

- **Đã từng thấy X?** Một filter chỉ-thêm có thể phù hợp nếu đã add mọi khóa từng thấy và không yêu cầu “quên”.
- **X hiện còn tồn tại?** Filter chỉ-thêm có thể trả True cho một X đã bị xóa khỏi database. Khi đó bắt buộc **xác minh True ở nguồn hiện hành** nếu nghiệp vụ cần chính xác.

### 7.1. Chỉ thêm mãi làm tăng tỷ lệ bit 1

Khi hệ thống liên tục thêm khóa mới, mảng bit ngày càng bão hòa:

~~~text
Ban đầu:     0000000000000000
Sau ít khóa: 0010001011000010
Sau nhiều:   1110111111101111
Bão hòa:     1111111111111111
~~~

Bloom chuẩn không giảm số bit 1 khi database xóa khóa. Vì thế số lượng khóa **hiện hoạt động giảm** không có nghĩa tỷ lệ false positive của filter sẽ tự giảm.

Nếu câu hỏi là membership đối với tập đang hoạt động, các khóa từng được thêm rồi đã xóa cũng có thể tiếp tục nhận True. Một filter chứa tất cả lịch sử có thể trở nên kém hiệu quả dù database hiện chỉ còn ít khóa.

### 7.2. Giữ bit cũ không tự vi phạm no FN

Nếu filter đã biểu diễn đầy đủ mọi khóa hiện hoạt động và chưa có bit nào bị tắt, thì mọi khóa đang hoạt động vẫn có đủ vị trí bit bằng 1. Do đó **no FN vẫn giữ** đối với tập hiện hoạt động.

Sai số mới nằm ở phía **False Positive**: filter nghi ngờ rằng khóa đã xóa vẫn có. Đó là trade-off có thể chấp nhận được nếu nhánh True chỉ dẫn đến một lượt tra cứu chính xác.

### 7.3. Điều kiện độ bao phủ dữ liệu còn quan trọng hơn delete

Nếu một database thêm khóa X nhưng filter không nhận được add(X), query False cho X là **sai ở cấp ứng dụng**. Đó không phải do filter không biết xóa, mà do **tập biểu diễn không bao phủ tập cần hỏi**.

Một hệ thống đúng cần giải quyết riêng hai chiều thay đổi:

- **Insert mới:** đảm bảo mọi khóa hiện hoạt động được mã hóa trước khi tin kết quả False.
- **Delete:** quyết định chấp nhận dấu vết cũ dẫn tới FP hay dùng một cơ chế xóa/tái xây an toàn.

## 8. Counting Bloom filter: thay bit bằng bộ đếm

Một cách khắc phục nguyên nhân mất thông tin về **số đóng góp ở mỗi vị trí** là thay mảng bit bằng **mảng counter**. Cấu trúc này gọi là **counting Bloom filter**.

Giả sử vẫn có m vị trí và h phép băm. Thay vì:

~~~text
bits[j] ∈ {0, 1}
~~~

ta dùng:

~~~text
counter[j] ∈ {0, 1, 2, ...}
~~~

Ý tưởng:

~~~text
ADD(x):
    for j in H_0(x), ..., H_(h-1)(x):
        counter[j] += 1

MIGHT_CONTAIN(x):
    for j in H_0(x), ..., H_(h-1)(x):
        if counter[j] == 0:
            return False
    return True

REMOVE_VERIFIED(x):
    # Chỉ được gọi khi hệ thống biết x thật sự đang hiện hữu.
    for j in H_0(x), ..., H_(h-1)(x):
        counter[j] -= 1
~~~

Đây là **ý tưởng cấu trúc**. Một cài đặt thực còn phải kiểm tra trạng thái, chống tràn/giảm âm, đồng bộ giao dịch và số lần thêm/xóa hợp lệ. Không được cho phép một hàm remove bất kỳ chỉ dựa vào kết quả might_contain.

### 8.1. Truy vết A và B với bộ đếm

Dùng cùng ví dụ:

~~~text
H(A) = {1,4}
H(B) = {4,6}

Ban đầu: mọi counter = 0.

Sau ADD(A):
counter[1]=1, counter[4]=1

Sau ADD(B):
counter[1]=1, counter[4]=2, counter[6]=1
~~~

Nếu A được **xóa đúng cách**:

~~~text
REMOVE_VERIFIED(A):
counter[1] giảm từ 1 xuống 0
counter[4] giảm từ 2 xuống 1

Kết quả:
counter[1]=0, counter[4]=1, counter[6]=1.
~~~

Lúc này:

- might_contain(A) nhìn thấy counter[1]=0 → **False**.
- might_contain(B) nhìn thấy counter[4]>0 và counter[6]>0 → **True**.

Counter cho bit 4 đã giữ đúng thông tin “vẫn còn một đóng góp tại vị trí này”, điều mảng bit 0/1 không thể thể hiện.

### 8.2. Bất biến của counter trong mô hình xóa hợp lệ

Gọi \(c_t[j]\) là bộ đếm ở vị trí j, và \(a_t(x)\) là **số lần xuất hiện hiện còn hiệu lực** của khóa x tại thời điểm t. Với update chèn/xóa hợp lệ và không tràn:

\[
\boxed{
c_t[j]=\sum_x a_t(x)\cdot
\#\{i:H_i(x)=j\}.
}
\]

Ký hiệu \(\#\{i:H_i(x)=j\}\) tính **số lần vị trí j xuất hiện trong h kết quả băm**, kể cả trường hợp một khóa băm trùng vị trí.

Nếu \(a_t(x)>0\), mỗi vị trí băm \(H_i(x)\) có ít nhất một đóng góp từ x, nên counter tại vị trí ấy **lớn hơn 0**:

\[
\boxed{
a_t(x)>0\Longrightarrow
\mathrm{mightContain}(x)=\mathrm{True}.
}
\]

Đó là chứng minh **không âm tính giả đối với các khóa vẫn còn ít nhất một lần xuất hiện**, trong điều kiện mọi add/remove hợp lệ, cùng hash và không có tràn hoặc mất cập nhật.

### 8.3. Hai khóa băm cùng toàn bộ vị trí vẫn có thể FP sau delete

Giả sử:

~~~text
H(A) = {1,4}
H(D) = {1,4}

ADD(A), ADD(D):
counter[1]=2, counter[4]=2

REMOVE_VERIFIED(A):
counter[1]=1, counter[4]=1

D vẫn hiện hữu.
~~~

Kết quả:

~~~text
might_contain(D) = True
might_contain(A) = True  # A đã xóa, nhưng băm trùng D.
~~~

**Counting Bloom hỗ trợ xóa hợp lệ và giữ no FN, không bảo đảm mọi khóa đã xóa đều trả False.** Trong ví dụ, A vẫn là một false positive so với tập đang hoạt động.

### 8.4. Hash trả trùng một vị trí thì sao?

Nếu một khóa sinh nhiều lần cùng một vị trí j trong h phép băm, cách diễn giải đếm nhất quán là:

- Khi add, tăng counter[j] **đúng số lần vị trí j xuất hiện**.
- Khi remove một lần xuất hiện hợp lệ, giảm **đúng số lần tương ứng**.
- Khi query, counter[j]>0 tại vị trí ấy là đủ.

Nếu muốn chỉ tăng mỗi **vị trí phân biệt** một lần, phải áp dụng quy tắc ấy **đồng nhất** ở cả add, remove và query. Không được add theo h lần nhưng remove theo một bộ vị trí khác do thay thuật toán xử lý trùng.

## 9. Vấn đề chưa được giải quyết: một lời gọi delete(x) có hợp lệ không?

**Counting Bloom có các bộ đếm, nhưng không biết chắc tên khóa nào đã add.** Hãy xét ví dụ A/B ở trên:

~~~text
Đã add A={1,4}, B={4,6}.

Counter:
c[1]=1, c[4]=2, c[6]=1.
~~~

Một khóa C **chưa add** có vị trí:

~~~text
H(C)={1,6}
~~~

Cả counter[1] và counter[6] đều >0, nên:

~~~text
might_contain(C) = True   # False positive.
~~~

Nếu ứng dụng viết:

~~~text
if counting_bloom.might_contain(C):
    counting_bloom.remove(C)
~~~

thì hành vi đó **không an toàn**. Xóa C dù C chưa có:

~~~text
counter[1]: 1 → 0
counter[6]: 1 → 0
counter[4]: vẫn 2

might_contain(A) = False  # Thiếu counter[1].
might_contain(B) = False  # Thiếu counter[6].
~~~

**Một lần xóa nhầm khóa C làm cả A và B thành âm tính giả.**

### 9.1. Vì sao kiểm tra counter >0 không đủ để cho phép xóa?

Các counter dương có thể **do khóa khác đóng góp**. Đó chính là cơ chế false positive. Vì vậy **might_contain(x) không thể đóng vai trò kiểm chứng delete(x)**.

Cần một hợp đồng bên ngoài chứng minh x thật sự đang hiện hữu, ví dụ:

- Một **dictionary chính xác** lưu số tham chiếu của từng khóa.
- Một nguồn dữ liệu có thẩm quyền đã xác nhận thao tác delete theo **ID cụ thể**.
- Một giao thức quản lý vòng đời chỉ phát sinh delete cho **những add đã được ghi nhận** và không phát delete thừa.
- Một cơ chế transaction/đồng bộ khiến những thao tác add/delete chính xác không bị mất, lặp không mong muốn hoặc đảo thứ tự.

### 9.2. Add trùng và remove một lần hay remove toàn bộ?

Nếu A được add ba lần, ta cần định nghĩa delete(A) có nghĩa:

- **Xóa một lần xuất hiện**: số đóng góp của A giảm từ 3 xuống 2.
- **Xóa hoàn toàn khóa khỏi tập**: phải giảm đúng **ba lần đóng góp** nếu counter đang đếm theo từng add.
- **Chèn theo ngữ nghĩa set**: add(A) lặp được coi là idempotent; khi đó phải có cách bảo đảm counter chỉ tăng **một lần** cho A, thường cần thông tin hiện diện chính xác.

Nếu không phân biệt ba hợp đồng này, các counter có thể bị tăng/giảm sai và gây false negative hoặc dấu vết thừa.

### 9.3. Xóa không xác thực là lỗi an toàn, không chỉ sai số thông thường

Trong mô hình counting Bloom với update hợp lệ, ta có thể chấp nhận **false positive** nhưng không chấp nhận **false negative**. Một lời gọi remove sai do dương tính giả phá bất biến, nên nó là **lỗi thao tác** chứ không phải “xác suất FN nhỏ được phép”.

Nếu nghiệp vụ không thể chứng minh khóa thực sự đã được thêm, tốt hơn là **không xóa ở tầng sketch**, hoặc tái xây từ nguồn chính xác khi cần làm sạch dấu vết.

## 10. Tràn/giảm âm bộ đếm và cập nhật đồng thời

Bộ đếm trong counting Bloom thường có độ rộng cố định, ví dụ 4 hoặc 8 bit. Khác với mảng bit của Bloom chuẩn, nó không tăng vô hạn được.

### 10.1. Tràn kiểu quay vòng (wraparound)

Giả sử counter 2-bit chỉ biểu diễn **0,1,2,3**. Nếu đã là 3 mà add làm nó quay về 0:

~~~text
counter[j]: 3 → 0 do overflow
~~~

thì một khóa vẫn còn hoạt động có thể nhìn thấy counter[j]=0 và bị **âm tính giả ngay sau add**.

Đây là vi phạm cốt lõi. Không được dùng bộ đếm có thể wrap mà không kiểm soát.

### 10.2. Bão hòa bộ đếm rồi xóa

Một số thiết kế **saturate** counter tại giá trị tối đa thay vì wrap:

~~~text
counter[j] = 3
ADD(x) cần tăng tiếp, nhưng counter vẫn là 3.
~~~

Tạm thời bão hòa **không làm counter về 0**, nhưng đã **mất thông tin về số đóng góp thực**. Nếu sau đó có nhiều thao tác delete, counter có thể giảm về 0 **trước khi các khóa thật ở vị trí ấy đã được xóa hết**, tạo FN.

Cần có chiến lược tràn rõ ràng: bộ đếm đủ rộng, vùng overflow, tái xây trước ngưỡng, hoặc từ chối update theo một hợp đồng an toàn. “Chặn ở max” không tự giải quyết vấn đề xóa.

### 10.3. Underflow vì delete quá số lần add

Nếu một khóa chỉ có một lần add nhưng bị delete hai lần, một counter có thể bị âm hoặc wrap về giá trị lớn. Tùy kiểu cài đặt, biểu diễn membership có thể sai hoặc thống kê bị mất nghĩa.

Cần chặn **delete dư** bằng nguồn thông tin chính xác về số lần add còn hiệu lực.

### 10.4. Cập nhật đồng thời

Mỗi add/remove thường cần cập nhật **h vị trí**. Hai luồng cập nhật cùng counter có thể **mất increment/decrement** nếu không có cơ chế nguyên tử. Query chạy khi một thao tác đang cập nhật dở có thể thấy trạng thái trung gian và trả False cho khóa được coi là đang hoạt động theo hợp đồng ứng dụng.

Do đó thiết kế cần xác định:

- **Thời điểm một add/delete hoàn tất và được công bố**.
- Cách đảm bảo increment/decrement ở từng vị trí không bị mất.
- Cách tránh query quan sát trạng thái chưa nhất quán với tập hiện hành.
- Cách khôi phục từ lỗi giữa chừng hoặc ghi trạng thái xuống đĩa.

Có thể dùng khóa, cập nhật nguyên tử cùng giao thức nhất quán cao hơn, hoặc xây/swap snapshot theo thiết kế cụ thể. **Chỉ đổi bit sang counter không tự làm hệ thống thread-safe**.


## 11. Python: phản ví dụ xóa sai trên bit và trên counter

Để thấy lỗi **một cách xác định**, ta dùng vị trí băm có sẵn, không dựa vào việc tình cờ tìm được va chạm của hash thật.

### 11.1. Bloom bit chuẩn: tắt bit khiến B bị FN

~~~python
positions = {
    "A": (1, 4),
    "B": (4, 6),
    "C": (1, 6),
}
bits = [0] * 8


def bit_add(key: str) -> None:
    for j in positions[key]:
        bits[j] = 1


def bit_might_contain(key: str) -> bool:
    return all(bits[j] == 1 for j in positions[key])


def unsafe_bit_delete(key: str) -> None:
    # Chỉ để minh họa lỗi; KHÔNG dùng trong Bloom bit chuẩn.
    for j in positions[key]:
        bits[j] = 0


bit_add("A")
bit_add("B")

assert bit_might_contain("A")
assert bit_might_contain("B")
assert bit_might_contain("C")  # C là false positive.

unsafe_bit_delete("A")

# B chưa hề bị xóa nhưng bit 4 đã về 0.
assert not bit_might_contain("B")  # False negative.
~~~

### 11.2. Counting Bloom: xóa một khóa chưa từng add

Dùng cùng positions nhưng có bộ đếm:

~~~python
counter = [0] * 8


def count_add(key: str) -> None:
    for j in positions[key]:
        counter[j] += 1


def count_might_contain(key: str) -> bool:
    return all(counter[j] > 0 for j in positions[key])


def unsafe_count_delete(key: str) -> None:
    # Không xác thực key có thật sự được add hay không.
    for j in positions[key]:
        counter[j] -= 1


count_add("A")
count_add("B")
assert counter[1] == 1
assert counter[4] == 2
assert counter[6] == 1

# C chưa được add, nhưng va chạm khiến query True.
assert count_might_contain("C")

unsafe_count_delete("C")

assert counter[1] == 0
assert counter[6] == 0
assert not count_might_contain("A")
assert not count_might_contain("B")
~~~

Dù đã có counter, **xóa theo một dương tính giả** vẫn có thể khiến cả hai khóa thật **âm tính giả**. Đây là lý do delete cần **bằng chứng khóa hiện hữu**, không chỉ kết quả might_contain.

## 12. Python: counting Bloom với kiểm tra khóa hiện hữu

Ví dụ sau dùng SHA-256 với tiền tố và chỉ số hash để tạo h vị trí có thể lặp lại. Để bảo đảm lời gọi delete hợp lệ trong bài học, mã lưu thêm **dictionary chính xác** theo dõi số lần add còn tồn tại của từng khóa.

**Đánh đổi phải nói rõ:** Dictionary chính xác khiến tổng bộ nhớ tăng theo số khóa. Đây là **mã giáo dục kiểm chứng bất biến**, không phải một triển khai tối ưu bộ nhớ của counting Bloom thuần túy. Trong sản phẩm, một nguồn có thẩm quyền bên ngoài có thể xác nhận việc xóa, nhưng vẫn cần bảo đảm nhất quán và số lần add/delete.

~~~python
from collections import Counter
import hashlib


class VerifiedCountingBloom:
    """Xóa một lần add hợp lệ trong mô hình tuần tự."""

    def __init__(self, slots: int, hash_count: int):
        if (
            isinstance(slots, bool)
            or not isinstance(slots, int)
            or slots <= 0
        ):
            raise ValueError("slots phải là int dương")
        if (
            isinstance(hash_count, bool)
            or not isinstance(hash_count, int)
            or hash_count <= 0
        ):
            raise ValueError("hash_count phải là int dương")

        self.m = slots
        self.h = hash_count
        self.counters = [0] * slots
        self.live_counts = {}

    def _positions(self, key: str):
        if not isinstance(key, str):
            raise TypeError("Ví dụ chỉ hỗ trợ khóa str")
        raw = key.encode("utf-8")
        for i in range(self.h):
            digest = hashlib.sha256(
                b"counting-bloom-v1|"
                + i.to_bytes(8, "big")
                + b"|"
                + raw
            ).digest()
            yield int.from_bytes(digest, "big") % self.m

    def add(self, key: str) -> None:
        needed = Counter(self._positions(key))
        for j, amount in needed.items():
            self.counters[j] += amount
        self.live_counts[key] = self.live_counts.get(key, 0) + 1

    def might_contain(self, key: str) -> bool:
        return all(
            self.counters[j] > 0
            for j in self._positions(key)
        )

    def remove_one(self, key: str) -> None:
        remaining = self.live_counts.get(key, 0)
        if remaining == 0:
            raise KeyError("Không có lần add còn hiệu lực")

        # Cùng một vị trí có thể xuất hiện nhiều lần trong h hash.
        needed = Counter(self._positions(key))
        if any(
            self.counters[j] < amount
            for j, amount in needed.items()
        ):
            raise RuntimeError("Counter bị hỏng; không được giảm âm")

        for j, amount in needed.items():
            self.counters[j] -= amount

        if remaining == 1:
            del self.live_counts[key]
        else:
            self.live_counts[key] = remaining - 1

    def contains_exactly(self, key: str) -> bool:
        return self.live_counts.get(key, 0) > 0


cbf = VerifiedCountingBloom(slots=128, hash_count=3)

cbf.add("A")
cbf.add("A")
cbf.add("B")
assert cbf.live_counts["A"] == 2
assert cbf.might_contain("A")
assert cbf.might_contain("B")

cbf.remove_one("A")
assert cbf.live_counts["A"] == 1
assert cbf.might_contain("A")

cbf.remove_one("A")
assert not cbf.contains_exactly("A")

# A sau xóa vẫn có thể trả True do trùng hash với khóa khác.
# Chỉ kiểm tra không FN cho khóa B đang hiện hữu.
assert cbf.might_contain("B")

try:
    cbf.remove_one("A")
except KeyError:
    pass
else:
    raise AssertionError("Không được xóa thừa")

try:
    cbf.remove_one("never-added")
except KeyError:
    pass
else:
    raise AssertionError("Không được xóa khóa chưa add")

# Mọi khóa còn một lần add đều phải query True.
for key in cbf.live_counts:
    assert cbf.might_contain(key)
~~~

### 12.1. Bất biến được mã minh họa bảo vệ

Với update **tuần tự**, Python int không bị giới hạn vào một số bit máy cố định và các lời gọi remove_one chỉ được thực hiện khi live_counts[key] > 0:

- Mỗi lần add tăng đúng các counter của h vị trí.
- Mỗi lần remove_one hợp lệ giảm đúng một lần đóng góp của khóa.
- Vị trí hash lặp được xử lý nhất quán nhờ Counter.
- Mọi khóa có live_counts[key] > 0 vẫn có toàn bộ counter tương ứng > 0.
- Khóa chưa add, hoặc đã xóa hết, không thể được remove_one nữa.

Đây **không phải** một mô hình sẵn sàng cho đa luồng, crash recovery hoặc bảo mật. SHA-256 với các tiền tố khác nhau cũng không tự chứng minh tất cả điều kiện độc lập hash của công thức FPR lý tưởng.

### 12.2. Vì sao dictionary là một chi phí lớn?

Các counter chỉ cho biết **tổng đóng góp tại từng vị trí**. Dictionary bổ sung điều mà filter không tự suy ra: **khóa nào đang có và có bao nhiêu lần add hợp lệ**.

Nếu bỏ dictionary và dùng might_contain làm điều kiện xóa, ví dụ mục 11.2 có thể tái diễn. Trong hệ thống lớn, nguồn xác minh thường là database, log giao dịch hoặc quản lý ID chính xác bên ngoài bộ lọc. Cần cân nhắc rằng **một nguồn có thẩm quyền vẫn phải tồn tại** nếu nghiệp vụ đòi xóa có kiểm chứng.

### 12.3. Python int không giống counter 4-bit trong sản xuất

Python int lớn dần theo giá trị, nên mã không minh họa overflow của counter 4-bit hay 8-bit. Counting Bloom nén counter thường giới hạn độ rộng để giảm RAM; khi tràn/underflow, bất biến có thể hỏng. Phải thiết kế **kích thước bộ đếm và chính sách tràn** trước khi triển khai.

## 13. Độ phức tạp và đánh đổi bộ nhớ

Với m vị trí và h phép băm mỗi khóa:

| Cấu trúc | Add | Query | Delete | Bộ nhớ chính |
| --- | --- | --- | --- | --- |
| **Bloom bit chuẩn** | O(h) | O(h) | Không có delete an toàn tùy ý | **m bit** |
| **Counting Bloom** | O(h) | O(h) | O(h) khi update hợp lệ | **m × b bit**, counter b-bit |
| **Set hash chính xác** | O(1) trung bình | O(1) trung bình | O(1) trung bình | Theo số khóa và payload |
| **Bloom xây lại từ snapshot** | O(Nh) cho N khóa | O(h) | Tái xây chứ không delete trực tiếp | m bit + nguồn khóa |
| **Bloom theo phân vùng thời gian** | O(h) mỗi lần thêm | O(h × số phân vùng cần tra) | Bỏ cả phân vùng đủ điều kiện | Tổng m của các phân vùng |

Nếu có **m=1.000.000 vị trí**:

~~~text
Bloom bit:       1 000 000 bit ≈ 0,119 MiB.
Counting 4-bit:  4 000 000 bit ≈ 0,477 MiB.
Counting 8-bit:  8 000 000 bit ≈ 0,954 MiB.
~~~

Chưa tính hash/seed, metadata, vùng nhớ của đối tượng, nguồn xác minh và chi phí đồng bộ. Python list[int] sử dụng nhiều bộ nhớ hơn một mảng counter được đóng gói vào đúng 4 bit/ô.

**b là số bit mỗi counter**, khác với **bit trên mỗi khóa** trong công thức định cỡ Bloom. Nếu cùng ngân sách RAM tổng, counting Bloom có thể dùng ít vị trí hơn Bloom bit, khiến xác suất FP thay đổi.

### 13.1. O(h) không bao gồm xác thực xóa

Một remove hợp lệ có thể cập nhật h counter, nhưng để xác minh khóa có thật và số lần add còn hiệu lực có thể phải truy vấn một **nguồn chính xác** hoặc giao dịch khác. Không được cộng gộp mọi chi phí này thành “xóa luôn O(1)” chỉ vì h cố định.

### 13.2. Độ dài khóa và CPU

Nếu tính h hash bằng cách quét toàn bộ khóa dài L byte ở mỗi lần, chi phí có thể **O(hL)**; nếu hash khóa coi là O(1), add/query/remove là O(h). Bộ nhớ phụ để mã hóa khóa/digest có thể phụ thuộc L.

### 13.3. Counter rộng hơn có trực tiếp giảm FPR không?

Không nhất thiết. Với cùng m vị trí và h, cấu trúc đếm đang hoạt động hợp lệ, phép kiểm tra counter>0 có cơ chế va chạm gần giống kiểm tra bit=1. Counter rộng hơn giúp biểu diễn **số đóng góp** và tránh overflow, không tự tăng số vị trí hay loại va chạm.

Để so công bằng, phải dùng **cùng ngân sách bộ nhớ tổng** và cùng workload, thay vì cùng m mà bỏ qua việc counting Bloom tốn nhiều bit hơn.


## 14. Những cách hỗ trợ xóa mà không phá bất biến

Không có một cách duy nhất phù hợp mọi hệ thống. Cần xác định **khóa có thật sự bị xóa về mặt nghiệp vụ không**, tần suất xóa, khả năng truy cập nguồn dữ liệu chính xác, thời gian lưu dữ liệu, và mức false positive có thể chấp nhận.

### 14.1. Chỉ dùng Bloom làm bộ lọc trước nguồn chính xác

Nếu xóa hiếm, cách đơn giản nhất là **không sửa Bloom khi delete**, chỉ xóa ở nguồn chính xác:

~~~text
Truy vấn X
   |
   v
Bloom.might_contain(X)?
   |
   +-- False --> Không có, nếu Bloom bao phủ đầy đủ tập hiện hoạt động
   |
   +-- True ---> Tra set/DB chính xác
                   |
                   +-- Có: trả có
                   +-- Không: trả không
~~~

Sau delete(A), Bloom có thể vẫn trả True cho A; tầng nguồn thật trả False. **Kết quả cuối vẫn chính xác**. Đổi lại, ngày càng nhiều khóa đã xóa làm filter trả True không cần thiết, khiến lượng lookup thật tăng.

Phải đảm bảo mọi khóa **hiện có trong DB** đều đã được add vào filter tương ứng. Nếu DB thêm khóa nhưng Bloom chưa cập nhật, nhánh False có thể làm ứng dụng trả sai, độc lập với vấn đề xóa.

### 14.2. Tái xây bộ lọc từ snapshot chính xác

Nếu có danh sách khóa hiện hoạt động, có thể:

1. Chụp tập khóa **S_snapshot** ở một phiên bản dữ liệu xác định.
2. Ước lượng n = số khóa phân biệt của snapshot.
3. Chọn m/h theo FPR mục tiêu, tạo **filter mới rỗng**.
4. Add toàn bộ khóa trong snapshot vào filter mới.
5. Bổ sung **delta cập nhật** được ghi nhận trong thời gian xây nếu cần đại diện dữ liệu mới.
6. Công bố filter mới cùng version nguồn mà nó bao phủ.
7. Chỉ sau khi chuyển đọc an toàn, bỏ filter cũ.

~~~text
Tại t0, DB snapshot: {A, B, C}
Bloom_old có lịch sử: A, B, C, D, E, F (D/E/F đã xóa).

Bloom_new được xây từ {A, B, C}.
Bloom_new không cần giữ bit của D/E/F.

Tuy nhiên D/E/F vẫn có thể là FP do va chạm với A/B/C.
~~~

**Tái xây không bảo đảm mọi khóa đã xóa đều trả False**, nhưng làm giảm dấu vết lịch sử không cần thiết, thường giúp FPR gần với mức thiết kế theo số khóa hiện hành.

### 14.3. Phân vùng bất biến theo thời gian

Nếu dữ liệu tự hết hạn **theo phân vùng nguyên khối**, có thể tạo Bloom cho từng ngày hoặc từng phiên bản:

~~~text
Day 1: Bloom_1  (khóa thuộc ngày 1)
Day 2: Bloom_2  (khóa thuộc ngày 2)
Day 3: Bloom_3  (khóa thuộc ngày 3)

Query "đã thấy trong 3 ngày gần nhất":
    Trả True nếu một trong ba filter trả True.
    Trả False chỉ khi cả ba filter đều trả False.
~~~

Khi Day 1 hết hạn hoàn toàn, bỏ **Bloom_1** mà không phải tắt bit riêng của từng khóa. Đây là **xóa cả phân vùng**, không phải delete tùy ý của một khóa trong filter.

Cần chú ý cửa sổ trượt theo giờ phút: nếu bỏ cả ngày khi chỉ một phần ngày hết hạn, có thể **bỏ sót sự kiện còn trong cửa sổ**. Phân vùng càng nhỏ có thể giảm sai lệch thời gian nhưng làm tăng số filter/query/metadata.

### 14.4. Cùng khóa xuất hiện ở nhiều phân vùng

Nếu X thuộc Day 1 và Day 3, bỏ Day 1 không khiến X biến mất khỏi truy vấn ba ngày vì Day 3 vẫn chứa X.

Tuy nhiên, nếu nghiệp vụ hỏi **“X hiện có trong bảng khách hàng”** chứ không phải **“X có sự kiện trong cửa sổ thời gian”**, dùng phân vùng theo ngày có thể không ánh xạ đúng semantics của bảng hiện tại. Phải định nghĩa **tập mà mỗi filter biểu diễn** và quy tắc truy vấn trước khi áp dụng xóa phân vùng.

### 14.5. Counting Bloom với kiểm chứng remove

Nếu xóa thường xuyên nhưng không thể tái xây liên tục, counting Bloom là một ứng viên, với điều kiện:

- Biết chính xác **khóa nào đang có**, số lần add còn hiệu lực hoặc quy tắc set semantics.
- Counter đủ rộng, có chiến lược khi đạt ngưỡng.
- Không cho phép delete khóa được phát hiện chỉ bằng might_contain.
- Giao thức cập nhật tránh missing/duplicate writes, cập nhật đồng thời và crash recovery.
- Mọi máy/replica nhất quán về **hash, seed, encoding, số counter và version**.

Nếu yêu cầu **danh sách khóa hoặc membership chính xác tuyệt đối**, một set/hash index hoặc database chính xác vẫn có thể hợp lý hơn.

### 14.6. Cuckoo filter và các cấu trúc khác

**Cuckoo filter** lưu fingerprint trong các bucket và có thể hỗ trợ xóa một fingerprint theo thuật toán của biến thể phù hợp. Nhưng fingerprint cũng có thể **va chạm**; xóa dựa trên một câu trả lời gần đúng cho khóa không hiện hữu có thể xóa nhầm dấu vết của khóa khác.

Ngoài ra có thể gặp giới hạn tỷ lệ lấp đầy, insert thất bại hoặc chi phí dịch chuyển tùy triển khai. Vì vậy không được hiểu “có API delete” là “mọi lời gọi delete tùy ý đều an toàn tuyệt đối”.

**Stable Bloom filter** hoặc cơ chế giảm bit/counter theo thời gian có thể cố ý quên thông tin để giới hạn bộ nhớ trong stream; đổi lại, chúng có thể **cho phép âm tính giả đối với khóa đã thấy trước đó**. Đây là một **hợp đồng khác** với Bloom chuẩn insert-only.

## 15. Xóa logic bằng tombstone: có cần tính đúng theo phiên bản không?

Một số hệ thống dùng **tombstone** (dấu xóa) hoặc một tập chứa **khóa đã xóa**. Điều này không trực tiếp làm các bit Bloom biến mất; nó thay đổi quy trình đọc.

### 15.1. Tombstone chính xác có thể lọc những dương tính cũ

Ví dụ khi đã biết A bị xóa:

~~~text
Bloom_old(A) = True
Exact_tombstones.contains(A) = True

Kết luận ở lớp ứng dụng:
    A đã bị xóa trong phiên bản dữ liệu đang xét.
~~~

Nếu tombstone lưu chính xác và ứng dụng biết thứ tự version, nó có thể tránh tra một nguồn khác. Nhưng tombstone **không xóa bit của Bloom**.

### 15.2. Tái chèn cùng khóa là trường hợp khó

Giả sử:

~~~text
T1: INSERT(A)
T2: DELETE(A), ghi tombstone
T3: INSERT(A) lần nữa
~~~

Nếu giữ tombstone cũ mà cứ thấy A thì trả “đã xóa”, ứng dụng sẽ trả **âm tính sai** dù A đã được tái chèn.

Do đó xóa logic cần **version/sequence number, quy tắc cuối-cùng-thắng hoặc thứ tự giao dịch**, cùng cơ chế xóa/ghi đè tombstone khi tái chèn phù hợp. Bloom chỉ giúp lọc ứng viên; nó không giải quyết **ngữ nghĩa dữ liệu sống/chết theo thời gian**.

### 15.3. Không được dùng một bộ lọc gần đúng làm “tập đã xóa” để chặn chắc chắn

Nếu dùng một Bloom thứ hai để ghi ID đã xóa và ra quyết định:

~~~text
if deleted_filter.might_contain(X):
    return "không tồn tại"
~~~

thì một **false positive của deleted_filter** có thể khiến khóa X còn hoạt động bị kết luận là đã xóa — tạo **âm tính sai ở cấp ứng dụng**.

Chỉ có thể dùng deleted_filter để **gợi ý xác minh tombstone chính xác**, không để đưa ra phủ định chắc chắn.

## 16. Nhất quán giữa filter và database khi thêm/xóa đồng thời

### 16.1. Hai chiều cập nhật không đối xứng

**Đối với add:** Nếu DB đã có X nhưng Bloom chưa nhận add, tin Bloom False có thể loại nhầm khóa đang tồn tại. Cần đảm bảo **filter bao phủ tập được hỏi**.

**Đối với delete:** Nếu DB đã xóa X nhưng Bloom chưa giảm dấu vết, Bloom có thể trả True. Nếu nhánh True luôn được xác minh bằng DB, sai lệch ấy chủ yếu **làm tăng lượt tra cứu** chứ không làm kết luận cuối sai.

Sự bất đối xứng này là một lợi thế thực dụng của kiến trúc **Bloom chỉ-thêm + nguồn chính xác** trong môi trường cần đúng kết quả.

### 16.2. Race giữa add và delete

Một hệ thống cho phép:

~~~text
T1: DELETE(A) từ DB
T2: ADD(A) trở lại DB
T3: Worker nhận thông điệp DELETE(A) cũ
~~~

Nếu counting Bloom xử lý T3 như một delete mới mà không xét **version/sequence**, nó có thể giảm counter của A sau lần add tại T2, khiến khóa còn hoạt động bị âm tính giả.

Cần đảm bảo các update có **thứ tự hợp lệ, tính idempotent hoặc dedup thông điệp**, và có quy tắc phục hồi khi xử lý trùng hoặc muộn.

### 16.3. Crash khi đang cập nhật nhiều counter

Một add(x) phải tăng h vị trí. Nếu tiến trình chết sau vài vị trí, một khóa được DB coi là đã thêm có thể chưa có đủ counter >0. Tương tự, một delete(x) chết giữa chừng có thể làm các counter/nguồn chính xác bất nhất.

Cần chọn một hợp đồng:

- Chỉ công bố cập nhật sau khi filter đã đạt trạng thái đầy đủ.
- Dùng transaction/journal và replay đúng version.
- Dùng snapshot bất biến mới rồi **swap** theo quy tắc nhất quán.
- Khi không chứng minh được filter đủ cập nhật, **bypass nhánh False** và tra nguồn thật.

### 16.4. Nhiều replica, hash và serialization

Nếu một replica dùng seed/hash version khác, cùng khóa có thể đi tới vị trí khác. Với counting Bloom, còn cần thống nhất **độ rộng counter, thứ tự byte, cách xử lý overflow và số lần cập nhật**.

Không được OR hoặc cộng các mảng theo vị trí giữa những filter **không tương thích** rồi dùng chúng như một filter duy nhất.

### 16.5. Khi nào có thể chấp nhận không xóa khỏi Bloom?

Nếu truy vấn cần **đúng kết luận cuối** nhưng lưu trữ nguồn có thẩm quyền sẵn có, và số khóa đã xóa không làm Bloom bão hòa quá nhanh, **không xóa bit** có thể là lựa chọn đơn giản và an toàn hơn nhiều so với dùng counting Bloom.

Phương án này cần giám sát **FPR đo trên tập hiện hoạt động** và **số lookup nguồn thật**; khi quá cao thì tái xây. Không có ngưỡng tái xây chung cho mọi workload.

## 17. Chọn giải pháp theo yêu cầu: một bảng quyết định

| Nhu cầu | Phương án cân nhắc | Điều cần kiểm tra |
| --- | --- | --- |
| Chỉ hỏi “đã từng thấy?”; không cần quên | Bloom bit chuẩn | Tập lịch sử được add đầy đủ; FPR phù hợp |
| Xóa hiếm; nguồn khóa chính xác sẵn có | Bloom bit + xác minh DB + tái xây định kỳ | Không tin True như tồn tại chắc chắn |
| Xóa nhiều, cần giữ summary nhỏ | Counting Bloom và xác thực delete | Counter overflow/underflow, duplicate add, concurrency |
| Khóa tự hết hạn theo ngày/phiên bản | Bloom per partition/epoch | Phạm vi thời gian, loại phân vùng an toàn |
| Muốn liệt kê tất cả khóa, xóa và lookup chính xác | Set/hash index hoặc DB chính xác | Bộ nhớ/chi phí lưu dữ liệu |
| Muốn xóa theo fingerprint, chấp nhận membership gần đúng | Cuckoo filter hay biến thể phù hợp | Xóa khóa có thật, va chạm fingerprint và insert failure |
| Luồng không giới hạn, chấp nhận quên theo thời gian | Stable/aging filter | Có thể phát sinh **false negative** |
| Chính sách cấp quyền/thanh toán/định danh cần đúng tuyệt đối | Nguồn xác minh chính xác | Không dùng FP làm căn cứ quyết định |
| Muốn “một khóa đã xóa luôn False, khóa hoạt động luôn True” | Chỉ mục chính xác/phân biệt khóa đủ thông tin | Bloom gần đúng không cho hợp đồng hai phía |

### 17.1. Trước khi chọn counting Bloom, hỏi gì?

1. Xóa theo **ngữ nghĩa tập** hay **mỗi lần xuất hiện**?
2. Ai xác nhận delete(x) **hợp lệ**?
3. Có add trùng hoặc event xử lý lại do retry không?
4. Bộ đếm tối đa là bao nhiêu và có thể **tràn** không?
5. Độ rộng counter có vượt ngân sách RAM không?
6. Các update có đồng bộ giữa DB/filter/replica không?
7. Query có thể thấy add/remove đang chạy dở không?
8. Đã có quy trình version/replay khi lỗi hay restart chưa?
9. FP sau delete có được chấp nhận không?
10. Nếu đã cần lưu toàn bộ khóa chính xác, counting Bloom còn **tiết kiệm chi phí tổng** không?

Nếu chưa trả lời được, không nên coi “có delete API” là lý do đủ để chọn counting Bloom.


## 18. Kiểm thử delete: phải kiểm tra điều gì?

Đối với một bộ lọc gần đúng có xóa, điều quan trọng nhất không phải là **khóa đã xóa có trả False hay chưa**, mà là **không khóa còn hoạt động nào bị False**.

### 18.1. Hai tập kiểm tra khác nhau

Gọi:

- **S_active**: Tập khóa hiện còn ít nhất một lần xuất hiện hợp lệ.
- **S_inactive**: Những khóa đã xóa hoặc chưa bao giờ được thêm.

Cần kiểm tra:

\[
\boxed{
\forall x\in S_{\mathrm{active}}:
\mathrm{mightContain}(x)=\mathrm{True}.
}
\]

Đây là điều kiện **không âm tính giả**.

Với \(x\in S_{\mathrm{inactive}}\), có thể nhận True vì false positive; **không được assert tất cả khóa inactive phải False** nếu cấu trúc vẫn là approximate membership.

Nếu muốn đo FPR theo tập đang hoạt động:

\[
\widehat{\mathrm{FPR}}=
\frac{\#\{x\in S_{\mathrm{sample,inactive}}:
\mathrm{mightContain}(x)=\mathrm{True}\}}
{|S_{\mathrm{sample,inactive}}|}.
\]

Mẫu inactive cần có nhãn sự thật và phân bố phù hợp workload. Có thể phân riêng **khóa chưa từng thấy** và **khóa đã xóa** vì chúng có hành vi khác khi Bloom chỉ-thêm giữ dấu vết lịch sử.

### 18.2. Bài kiểm tra có nguồn chính xác

Đoạn Python sau dùng lớp **VerifiedCountingBloom** ở mục 12. Nguồn chính xác của bài kiểm tra là live_counts của lớp ấy; những thao tác xóa sai phải bị từ chối.

~~~python
cbf = VerifiedCountingBloom(slots=256, hash_count=3)

operations = [
    ("add", "A"),
    ("add", "B"),
    ("add", "A"),
    ("add", "C"),
    ("remove", "A"),
    ("remove", "B"),
    ("add", "B"),
    ("remove", "A"),
]

for action, key in operations:
    if action == "add":
        cbf.add(key)
    else:
        cbf.remove_one(key)

    # Điều kiện không FN sau MỌI thao tác hợp lệ.
    for active_key in cbf.live_counts:
        assert cbf.might_contain(active_key)

# Cuối cùng C và B còn hoạt động, A đã xóa hết.
assert cbf.contains_exactly("C")
assert cbf.contains_exactly("B")
assert not cbf.contains_exactly("A")

assert cbf.might_contain("C")
assert cbf.might_contain("B")

# KHÔNG có assert cbf.might_contain("A") is False:
# A đã xóa vẫn có thể nhận True do va chạm hash.
~~~

### 18.3. Các tình huống biên cần thử

| Tình huống | Kết quả/điều kiện cần giữ |
| --- | --- |
| Add A một lần, remove A một lần | Không còn A trong nguồn chính xác; filter có thể FP cho A |
| Add A ba lần, remove A hai lần | A còn một lần xuất hiện, **phải True** |
| Remove A chưa từng add | Phải từ chối, không được giảm counter |
| Remove A lần thứ hai sau khi xóa hết | Phải từ chối, tránh underflow |
| A và B chia sẻ một số vị trí | Remove A không được làm B False |
| A và B có cùng toàn bộ vị trí | Remove A giữ B True; A có thể vẫn True |
| Một khóa có vị trí băm trùng trong h hash | Increment/decrement phải đối xứng |
| Counter đạt giá trị tối đa | Phải có chính sách overflow an toàn |
| Hai luồng cùng cập nhật một counter | Không mất increment/decrement |
| Query chạy giữa một remove nhiều vị trí | Phải có hợp đồng snapshot/linearization |
| Restart sau crash giữa một update | Phải replay hoặc khôi phục nhất quán |
| Delete rồi reinsert cùng khóa | Version/tombstone phải không phủ định khóa mới |
| Bloom cũ với hash/seed mới | Không được dùng lại bit/counter thiếu tương thích |
| Loại nguyên phân vùng thời gian | Không được bỏ dữ liệu vẫn thuộc cửa sổ truy vấn |

### 18.4. Những đại lượng nên giám sát

- Số khóa **hiện hoạt động** và số lần add còn hiệu lực.
- Tỷ lệ bit 1 hoặc số counter >0.
- Phân bố mức counter và số lần **chạm ngưỡng tràn**.
- Số thao tác remove bị từ chối do khóa không tồn tại.
- Số thao tác update bị trùng hoặc sai thứ tự.
- FPR trên khóa inactive có nhãn sự thật.
- Độ trễ add/query/delete và chi phí xác minh nguồn chính xác.
- Phiên bản snapshot/hash/encoding, số replica không đồng bộ.
- Số lần phải tái xây filter và chi phí duy trì song song bản cũ/mới.

Các chỉ số giúp đánh giá chi phí thực tế. Nhưng **một lỗi FN đối với khóa hoạt động đã add thành công** trong hợp đồng không FN là vấn đề **tính đúng đắn**, không thể được xử lý chỉ bằng cách nâng FPR mục tiêu hoặc coi nó là sai số thống kê cho phép.

## 19. Bảng lỗi suy luận và triển khai thường gặp

| Sai lầm | Hậu quả | Cách hiểu/sửa đúng |
| --- | --- | --- |
| “Muốn delete thì tắt h bit của khóa.” | Có thể tắt bit dùng chung, gây FN cho khóa khác | Bloom bit chuẩn **không delete tùy ý** |
| “Chỉ tắt bit chưa từng trùng trong ví dụ của tôi là đủ.” | Không biết quyền sở hữu trong filter, có trường hợp không có bit riêng | Cần metadata hoặc thiết kế khác |
| “Hai khóa cùng vị trí vẫn xóa một khóa để nó False được.” | Tắt vị trí khiến khóa còn sống False | Chấp nhận FP hoặc dùng nguồn chính xác |
| “Không tắt bit nghĩa là bộ lọc bị hỏng.” | Không; chỉ có dấu vết lịch sử dẫn tới FP | Định nghĩa đúng tập ever-seen/current |
| “DB xóa X thì Bloom tự cập nhật.” | Bit/counter không biết transaction DB | Xây quy trình cập nhật hoặc xác minh |
| “Counter lớn hơn 0 nghĩa là khóa chắc chắn có.” | Các khóa khác có thể tạo số đếm dương | Counting Bloom vẫn có FP |
| “Có thể delete khi might_contain True.” | Xóa một FP có thể giảm nhầm counter và gây FN | Delete cần xác minh khóa đang hoạt động |
| “Nếu xóa A thì might_contain(A) phải False.” | A có thể trùng toàn bộ dấu vết với khóa B còn sống | FP sau delete là có thể chấp nhận |
| “Add trùng là vô hại trong counting Bloom.” | Nếu tăng counter lặp nhưng xóa theo set semantics, còn dấu vết thừa | Chọn rõ multiplicity/set semantics |
| “Counter 4-bit không tràn vì chỉ lưu tần suất nhỏ.” | Va chạm nhiều khóa có thể làm cùng counter tăng lớn | Dự báo tải, chính sách overflow |
| “Saturate tại max là xóa luôn an toàn.” | Mất số đóng góp thực, delete về sau có thể tạo FN | Rebuild/overflow tracking |
| “Counter âm chỉ là sai số xấp xỉ.” | Có thể phá ngữ nghĩa và chứng minh no FN | Chặn underflow và xóa thừa |
| “Hai luồng update cùng ô chắc chắn cộng đúng.” | RMW không nguyên tử có thể mất cập nhật | Atomic/lock/giao thức nhất quán |
| “Query đang chạy giữa delete vẫn có nghĩa rõ ràng.” | Có thể thấy trạng thái nửa cập nhật | Định nghĩa thời điểm công bố |
| “Đổi m/h/hash rồi giữ counter cũ là hợp lệ.” | Add/query không còn cùng vị trí | Tái xây/chuyển version |
| “Counting Bloom cùng m chỉ tốn thêm ít metadata.” | Mỗi vị trí trở thành counter nhiều bit | Tính **m×b bit** và nguồn xác minh |
| “Đã có Bloom thì có thể tái xây từ bit array.” | Không khôi phục được danh sách khóa gốc | Cần nguồn khóa chính xác |
| “Xóa cả phân vùng thời gian luôn an toàn.” | Cửa sổ trượt có thể vẫn cần một phần phân vùng | Chọn granularities và ngữ nghĩa đúng |
| “Tombstone vĩnh viễn đúng cả khi khóa tái chèn.” | Có thể phủ định khóa mới đang hoạt động | Version/reinsert semantics |
| “Bloom của tập đã xóa có thể trực tiếp chặn khóa.” | FP của bộ lọc xóa tạo sai âm tính ở ứng dụng | Xác minh tombstone chính xác |
| “Stable Bloom vẫn luôn no FN.” | Cơ chế decay có thể cố ý quên khóa | Chọn hợp đồng chấp nhận FN |
| “Cuckoo filter có delete nên mọi delete tùy ý đều đúng.” | Fingerprint collision, yêu cầu khóa hiện hữu và điều kiện triển khai | Xác minh preconditions |
| “Đo FPR trên toàn bộ request là đúng.” | Lẫn positive vào mẫu số | FPR tính trên negative thật |
| “Mọi khóa inactive phải False.” | Xấp xỉ membership cho phép FP | Chỉ yêu cầu **mọi khóa active True** |
| “Một FN trong counting Bloom là chấp nhận vì đây là sketch.” | Với update hợp lệ/no overflow, no FN là bất biến | Điều tra vi phạm cập nhật |
| “Kết quả True đủ chứng minh đã thanh toán hoặc được quyền.” | False positive gây quyết định sai | Luôn tra nguồn có thẩm quyền |

**Checklist ngắn:** Trước một lệnh delete, phải biết **khóa có thật không, còn bao nhiêu lần add, bộ đếm có thể tràn không, có va chạm không, update có đồng bộ không, và phần tử được xóa có thể vẫn trả True hay không**.


## 20. Bài tập tự luyện có đáp án

### Nhóm A — Nền tảng và bất biến

**Bài 1 — Hai loại câu hỏi.** Sự khác nhau giữa “X đã từng được add” và “X hiện còn trong database” là gì?

*Đáp án:* Bloom chỉ-thêm giữ **dấu vết lịch sử**; database có thể xóa khóa. Bloom True không chứng minh X **hiện còn hoạt động**.

**Bài 2 — Query False.** Trong Bloom chỉ-thêm hợp lệ, một khóa đã add thành công có thể query False không?

*Đáp án:* **Không**, vì tất cả vị trí đã được bật và không bị tắt. Điều này cần hash, encoding và trạng thái nhất quán.

**Bài 3 — Query True.** Khóa C chưa từng được add nhưng được trả True. Đây là hiện tượng gì?

*Đáp án:* **False positive** do các khóa khác có thể đã bật đủ bit của C.

**Bài 4 — Xóa không tắt bit.** Database xóa A, Bloom bit vẫn không đổi. Nếu query A trả True, nó có nhất thiết là bug của Bloom không?

*Đáp án:* **Không**. Nó phản ánh dấu vết đã từng add; so với tập DB đang hoạt động, đây có thể là **dương tính giả sau xóa**.

**Bài 5 — Xóa bằng reset bit.** Vì sao tắt tất cả vị trí của A không phải delete an toàn trong Bloom chuẩn?

*Đáp án:* Những bit ấy có thể **được khóa B đang hoạt động dùng chung**; tắt chúng gây âm tính giả cho B.

**Bài 6 — Bất biến.** Công thức đơn điệu của Bloom insert-only là gì?

*Đáp án:* \(B_{t+1}[j]\ge B_t[j]\) với \(B_t[j]\in\{0,1\}\). Không có chuyển **1→0**.

**Bài 7 — Phản đảo.** Từ “đã add ⇒ query True”, suy luận nào hợp lệ?

*Đáp án:* **Query False ⇒ chưa add vào tập filter biểu diễn**, nếu các tiền điều kiện được giữ.

**Bài 8 — Suy luận đảo.** Có được kết luận query True ⇒ khóa thực sự đã add không?

*Đáp án:* **Không**; false positive là phản ví dụ.

**Bài 9 — Add trùng khóa.** Bloom bit chuẩn có phân biệt A được add một lần và A được add ba lần không?

*Đáp án:* **Không**, vì cùng khóa bật lại các vị trí giống nhau; không lưu multiplicity.

**Bài 10 — Mảng bit thiếu thông tin gì?** Nêu hai loại thông tin cần cho delete mà bitarray không có.

*Đáp án:* **Số khóa/lần đóng góp đang dùng từng bit** và **danh tính/số lần hiện hữu của khóa được yêu cầu xóa**.

### Nhóm B — Phản ví dụ chia sẻ bit

**Bài 11 — Trạng thái sau add.** Với H(A)={1,4}, H(B)={4,6}, ban đầu toàn 0, những bit nào bằng 1 sau add A và B?

*Đáp án:* **{1,4,6}**.

**Bài 12 — Xóa A sai.** Nếu tắt cả bit 1 và bit 4, query B trả gì?

*Đáp án:* **False**, vì B cần bit 4 và bit 6; bit 4 đã bị tắt. Đây là **FN** cho B.

**Bài 13 — False positive C.** H(C)={1,6}, C chưa add; sau add A/B, query C trả gì?

*Đáp án:* **True**, vì bit 1 và 6 đều đã bật; C là một **FP**.

**Bài 14 — Không cần hash trùng toàn bộ.** Vì sao C có thể False Positive dù không có khóa đã add nào cùng toàn bộ H(C)?

*Đáp án:* Các bit của C có thể do **nhiều khóa khác nhau hợp lại** bật, không cần một khóa đơn lẻ có vector hash giống C.

**Bài 15 — Hai khóa cùng dấu vết.** H(A)=H(D)={1,4}; xóa A, giữ D. Có thể làm query A False và D True bằng cách chỉ thay các bit {1,4} không?

*Đáp án:* **Không**. Hai khóa cùng kiểm tra đúng những vị trí ấy; tắt một bit sẽ khiến D False.

**Bài 16 — Tắt bit riêng.** Trong một ví dụ nào đó, có bit chỉ A dùng nên tắt bit ấy không làm B sai. Có chứng minh Bloom chuẩn xóa tùy ý được không?

*Đáp án:* **Không**. Bloom không lưu quyền sở hữu bit; và có tình huống **không có bit riêng** để tắt.

### Nhóm C — Counting Bloom và các điều kiện xóa

**Bài 17 — Tác dụng counter.** Counting Bloom khác Bloom chuẩn ở dữ liệu lưu tại một vị trí như thế nào?

*Đáp án:* Counting Bloom lưu **bộ đếm đóng góp**, thay vì chỉ một bit 0/1.

**Bài 18 — Cập nhật.** Với H(A)={1,4}, H(B)={4,6}, sau add A/B các counter khác 0 có giá trị nào?

*Đáp án:* **c[1]=1, c[4]=2, c[6]=1**.

**Bài 19 — Delete A hợp lệ.** Với trạng thái bài 18, xóa một lần add(A) thì các counter còn gì?

*Đáp án:* **c[1]=0, c[4]=1, c[6]=1**. B vẫn trả True.

**Bài 20 — Xóa C sai.** C chưa add, H(C)={1,6}, nhưng might_contain(C) True sau add A/B. Nếu giảm counter của C thì chuyện gì xảy ra?

*Đáp án:* **c[1] và c[6] về 0**, khiến **A và B cùng bị âm tính giả** dù đang hoạt động.

**Bài 21 — Delete cần điều kiện gì?** Tại sao một lệnh delete không được chỉ dựa trên might_contain(x)?

*Đáp án:* Might_contain có thể là **false positive**. Cần chứng minh **x thực sự hiện hữu và còn quyền xóa** từ nguồn có thẩm quyền.

**Bài 22 — Add ba lần.** Nếu A đã add ba lần theo ngữ nghĩa multiset và được remove_one hai lần, A còn phải trả True không?

*Đáp án:* **Có**. Vẫn còn một lần add hợp lệ, nên mọi counter của A phải >0 nếu không lỗi tràn/cập nhật.


**Bài 23 — Xóa hết A nhưng A vẫn True.** H(A)=H(D)={1,4}, cả hai đã add. Counting Bloom remove A hợp lệ, D còn hoạt động. Query A có thể vẫn True không?

*Đáp án:* **Có**, vì bộ đếm ở cả hai vị trí vẫn được D duy trì. Đây là **FP sau delete** được phép.

**Bài 24 — Hash trùng vị trí.** Một khóa có h=3 nhưng băm vào {4,4,7}. Khi add/remove theo quy tắc tính đủ h lần, counter 4 phải tăng/giảm bao nhiêu?

*Đáp án:* **Hai lần** cho một lần add/remove, còn counter 7 một lần. Có thể dùng bảng số lần xuất hiện mỗi vị trí để thao tác đối xứng.

**Bài 25 — Overflow quay vòng.** Counter 2-bit tối đa 3, đang 3, bị tăng rồi quay về 0. Có thể làm khóa hiện hữu trở thành FN không?

*Đáp án:* **Có**. Query thấy counter 0 tại một vị trí bắt buộc; phải ngăn overflow.

**Bài 26 — Saturating counter.** Nếu giữ counter ở max thay vì tăng thêm, rồi sau này xóa nhiều khóa, điều gì có thể xảy ra?

*Đáp án:* Mất thông tin số đóng góp thực; counter có thể về 0 khi vẫn còn khóa cần nó, tạo **FN**.

**Bài 27 — Underflow.** Delete một khóa đã được xóa hết có hợp lệ không?

*Đáp án:* **Không**. Cần từ chối thao tác, tránh giảm counter vượt số lần add hợp lệ.

**Bài 28 — Cập nhật đồng thời.** Hai luồng cùng sửa một counter bằng đọc–sửa–ghi không nguyên tử có nguy cơ gì?

*Đáp án:* **Mất increment/decrement**, gây sai số đóng góp và có thể tạo FN. Cần đồng bộ với giao thức nhất quán phù hợp.

### Nhóm D — Kiến trúc xóa và vòng đời

**Bài 29 — Xóa ở DB, giữ Bloom.** Nếu database xóa A nhưng Bloom chỉ-thêm không đổi và nhánh True luôn tra DB, kết luận membership cuối có còn chính xác không?

*Đáp án:* **Có thể vẫn chính xác**, miễn filter bao phủ đầy đủ mọi khóa hiện còn và nhánh True được xác minh. Dấu vết A gây thêm FP/lookup.

**Bài 30 — Rebuild.** Muốn loại dấu vết các khóa đã xóa mà không reset từng bit, cần nguồn thông tin nào?

*Đáp án:* **Danh sách khóa hiện còn chính xác** để xây Bloom mới. Không thể khôi phục danh sách từ bitarray cũ.

**Bài 31 — Phân vùng ngày.** Muốn bỏ dữ liệu nguyên một ngày đã hết hạn. Cách nào cho phép không xóa từng bit?

*Đáp án:* **Bloom riêng cho từng phân vùng thời gian**; bỏ cả filter của ngày đó khi mọi dữ liệu của ngày đã hết hạn.

**Bài 32 — Cửa sổ trượt.** Nếu bỏ filter của cả một ngày trong khi một phần ngày đó vẫn thuộc cửa sổ 24 giờ gần nhất, điều gì có thể xảy ra?

*Đáp án:* **Bỏ sót khóa còn thuộc cửa sổ**; phải chọn độ hạt phân vùng hoặc quy trình xử lý thời gian đúng.

**Bài 33 — Tombstone cũ.** A bị xóa rồi được tái chèn; dùng tombstone cũ không version để luôn trả False cho A có thể gây điều gì?

*Đáp án:* **Âm tính sai cấp ứng dụng**; cần version/sequence và quy tắc reinsert.

**Bài 34 — Bloom của tập đã xóa.** Một deleted_filter gần đúng trả True cho B đang còn hoạt động. Có được kết luận B đã xóa không?

*Đáp án:* **Không**. Đó có thể là FP của deleted_filter, phải xác minh tombstone chính xác.

**Bài 35 — Stable Bloom.** Một filter chủ động làm bit/counter cũ suy giảm để giới hạn bộ nhớ có giữ bảo đảm không FN đối với mọi khóa từng thấy không?

*Đáp án:* **Không nhất thiết**. Cơ chế quên có thể cho phép FN; đây là một hợp đồng khác Bloom chỉ-thêm.

**Bài 36 — Bộ nhớ.** Với m=1.000.000 vị trí, counting Bloom 4-bit dùng bao nhiêu bit vùng counter và lớn hơn Bloom bit bao nhiêu lần?

*Đáp án:* **4.000.000 bit**, tức **4 lần** vùng bit của Bloom chuẩn có cùng số vị trí, chưa tính metadata.

### Nhóm E — Kiểm thử và lựa chọn đúng

**Bài 37 — Điều kiện kiểm thử sau delete.** Nếu có nguồn chính xác S_active, assertion quan trọng nhất cho một counting Bloom hỗ trợ xóa là gì?

*Đáp án:* **Mọi x trong S_active phải trả might_contain(x)=True**. Một FN là lỗi bất biến.

**Bài 38 — Khóa đã xóa có bắt buộc False?** Có nên assert mọi khóa vừa xóa đều nhận False không?

*Đáp án:* **Không**. Va chạm có thể khiến khóa đã xóa tiếp tục True; đây là FP được phép của cấu trúc gần đúng.

**Bài 39 — Lựa chọn cho thanh toán.** Có được dùng Bloom True như bằng chứng khách hàng đã thanh toán, hoặc deleted_filter True để từ chối thanh toán mới không?

*Đáp án:* **Không**. Các bộ lọc có thể FP; phải kiểm tra trạng thái ở nguồn chính xác có thẩm quyền.

**Bài 40 — Thiết kế hoàn chỉnh.** Một hệ thống có nhiều ID được thêm/xóa liên tục, cần không FN cho ID đang hoạt động nhưng chấp nhận FP gây thêm lookup. Hãy đề xuất hai phương án và điều kiện an toàn của mỗi phương án.

*Đáp án:* **Phương án 1:** Bloom bit chỉ-thêm làm prefilter, True xác minh nguồn chính xác, False chỉ được tin khi filter bao phủ đầy đủ tập hiện hoạt động; tái xây khi dấu vết cũ làm FP quá cao. **Phương án 2:** Counting Bloom với delete đã được xác thực, quản lý multiplicity, counter overflow/underflow, đồng bộ add/delete/version; mọi ID còn hoạt động phải tiếp tục query True. Nếu cần membership chính xác hai phía hoặc phải liệt kê ID, dùng set/DB chính xác.

## 21. Tổng kết và ghi nhớ

**Bloom filter chuẩn không hỗ trợ xóa một khóa tùy ý vì nó chỉ lưu bit 0/1, không lưu ai đang cần bit đó.** Một vị trí có thể được nhiều khóa dùng chung:

- **Giữ bit** sau delete: khóa đã xóa có thể tiếp tục nhận True. Đây là **dương tính giả so với tập hiện hành**, không tự tạo FN cho khóa còn sống.
- **Tắt bit** sau delete: có thể làm khóa khác mất một vị trí bắt buộc và nhận False. Đây là **âm tính giả**, phá bất biến Bloom chuẩn.
- **Hai khóa cùng toàn bộ vị trí băm:** không thể bắt khóa đã xóa False và khóa còn sống True chỉ bằng một mảng bit và phép query chuẩn.

Bất biến Bloom chỉ-thêm là:

\[
B_{t+1}[j]\ge B_t[j].
\]

Vì bit chỉ bật mà không tắt, một khóa đã add thành công luôn có đủ vị trí 1, cho nên không có âm tính giả trong mô hình đúng trạng thái. **Delete bằng reset bit phá bất biến đơn điệu** ấy.

**Counting Bloom filter** thay bit bằng counter, có thể giảm đúng đóng góp khi xóa **một lần add hợp lệ**. Nhưng nó **không tự biết khóa được yêu cầu xóa có thật sự hiện hữu hay không**; might_contain True vẫn có thể là FP. Xóa nhầm khóa FP, tràn/giảm âm counter, add/delete trùng, cập nhật không đồng bộ hoặc version sai đều có thể tạo FN.

Nếu không cần xóa ngay trên sketch, giải pháp thực tế thường đơn giản hơn: **giữ Bloom bit làm bộ lọc, xác minh nhánh True ở nguồn chính xác, và tái xây định kỳ từ tập khóa còn hoạt động**. Nếu dữ liệu hết hạn nguyên phân vùng, có thể bỏ **cả Bloom của phân vùng**. Nếu cần xóa thường xuyên, cân nhắc counting Bloom/cấu trúc hỗ trợ xóa kèm hợp đồng update nghiêm ngặt. Nếu cần đáp án đúng tuyệt đối cho cả True và False, dùng nguồn chính xác.

**Ghi nhớ:** **Bloom bit chuẩn chỉ biết “bit nào từng được bật”, không biết “bit này hiện thuộc về khóa nào”.** Do vậy, **không được xóa tùy ý bằng cách tắt bit**. Muốn hỗ trợ delete phải bổ sung thông tin hoặc thay đổi kiến trúc, đồng thời giữ đúng điều quan trọng nhất: **không được làm một khóa vẫn còn hoạt động trở thành âm tính giả**.
