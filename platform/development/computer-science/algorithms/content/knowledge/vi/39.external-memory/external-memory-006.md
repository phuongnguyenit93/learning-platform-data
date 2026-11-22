# Hợp, giao và nối dữ liệu đã sắp xếp

## 1. Bài toán trong môi trường ngoài bộ nhớ

Hai tệp dữ liệu lớn có thể chứa hàng triệu hoặc hàng tỷ dòng, lớn hơn RAM khả dụng. Nếu các bản ghi đã được **sắp theo cùng một khóa**, ta có thể đọc tuần tự từng tệp để tìm khóa xuất hiện ở ít nhất một bên, ở cả hai bên, chỉ ở một bên, hoặc ghép những bản ghi có khóa bằng nhau. Đây là nền tảng của **merge**, **set operations** và **sort-merge join** trong hệ xử lý dữ liệu ngoài bộ nhớ.

Các tác vụ không đồng nghĩa:

- **Union (hợp):** khóa có trong A hoặc B.
- **Intersection (giao):** khóa có trong cả A và B.
- **Difference (hiệu):** khóa thuộc A nhưng không thuộc B.
- **Symmetric difference (hiệu đối xứng):** khóa chỉ xuất hiện ở đúng một bên.
- **Join (nối quan hệ):** tạo cặp bản ghi (a,b) thỏa a.key=b.key; nếu khóa lặp thì phải sinh mọi cặp khớp.

Điểm mạnh của thứ tự đã sắp: khi đầu A nhỏ hơn đầu B, khóa hiện tại của A chắc chắn **không thể xuất hiện trong phần B chưa đọc**. Vì vậy hai con trỏ tiến một chiều là đủ, thay cho việc đưa toàn bộ dữ liệu vào HashSet hoặc HashMap.

Bài học sử dụng **khóa int có dấu, thứ tự tăng không giảm**. Phép tập hợp chỉ làm việc với khóa. Phép join làm việc với bản ghi gồm khóa và payload, và giữ đủ các bản ghi trùng khóa. Các mô hình liên quan SQL, multiset, bộ đệm và tệp tạm sẽ được giải thích rõ.

## 2. Phân biệt set semantics và bag semantics

Một **set** chỉ biết một khóa có xuất hiện hay không, trong khi **bag/multiset** còn biết khóa ấy xuất hiện bao nhiêu lần. Với các tệp đã sắp:

```text
A: [-2, 1, 1, 3, 5, 5, 8]
B: [-2, -2, 2, 3, 3, 7, 8, 8]

distinct(A): [-2, 1, 3, 5, 8]
distinct(B): [-2, 2, 3, 7, 8]

A union B (distinct) : [-2, 1, 2, 3, 5, 7, 8]
A intersect B        : [-2, 3, 8]
A minus B            : [1, 5]
A symmetric diff B   : [1, 2, 5, 7]
```

Các kết quả trên đều **distinct**: một khóa chỉ xuất tối đa một lần. Nếu nghiệp vụ yêu cầu giữ số lần lặp, mỗi khóa x có hai số lượng c_A(x), c_B(x):

| Phép toán bag | Số bản sao của khóa x |
|---|---|
| UNION ALL | c_A(x)+c_B(x) |
| INTERSECT ALL | min(c_A(x),c_B(x)) |
| EXCEPT ALL / A trừ B | max(c_A(x)−c_B(x),0) |
| Hiệu đối xứng theo đa tập | abs(c_A(x)−c_B(x)) |

SQL `UNION` thường loại dòng trùng, còn `UNION ALL` giữ bản sao; với `INTERSECT`, `EXCEPT` và các biến thể `ALL` cần kiểm dialect. **Một khóa xuất một lần trong giao tập hợp** hoàn toàn khác với **số cặp bản ghi join**.

Ví dụ A có hai bản ghi khóa 4, B có ba bản ghi khóa 4: giao distinct của hai cột khóa chỉ có một giá trị 4, nhưng inner join theo khóa 4 tạo **2×3=6 bản ghi**.

## 3. Phân tích theo khối I/O

Gọi N_A,N_B là số bản ghi hai tệp, N=N_A+N_B, Z là số bản ghi kết quả. Gọi B là số bản ghi cùng kích thước mỗi block; với bản ghi độ dài thay đổi, dùng tổng số **byte** thay vì chỉ đếm dòng.

Khi có bộ đệm đọc cho cả hai luồng và bộ đệm ghi cho output, một lượt merge tuần tự có thể đạt số I/O khối khoảng:

**Theta(ceil(N_A/B)+ceil(N_B/B)+ceil(Z/B)).**

Các phép union/intersection/difference theo set distinct có Z≤N, nên đọc/ghi tuần tự là gần tuyến tính. Join có thể có output J lên tới N_A·N_B, phải tính cả **J** trong thời gian và I/O.

Bộ nhớ lõi chỉ cần vài khóa hoặc bản ghi đang nhìn cùng buffer. Nhưng `BufferedReader.readLine()` vẫn tạo String có độ dài bằng cả dòng: nếu một dòng dài hàng GB, mô hình O(1) **số bản ghi** không đồng nghĩa O(1) **byte**. Hệ production cần giới hạn record size, parsing streaming hoặc định dạng nhị phân có kích thước rõ ràng.

Chi phí đọc tuần tự thường thuận lợi hơn nhiều lần seek ngẫu nhiên. Mặt khác, nếu hai tệp chưa sắp theo cùng comparator, phải đưa **chi phí external sort** vào bài toán trước khi áp dụng merge.

## 4. Hai con trỏ tiến một chiều

Giữ head a của luồng A và head b của luồng B. Tại mỗi bước:

- Nếu a<b: mọi khóa chưa đọc của B đều ≥b>a, nên a không còn cơ hội khớp với B.
- Nếu b<a: lập luận đối xứng.
- Nếu a=b: cả hai có khóa đó; xử lý kết quả và tiến cả hai.

Mỗi bước xử lý ít nhất một khóa, nên thuật toán kết thúc. Với set semantics, các duplicate liền nhau được gom thành một khóa distinct bằng cách **bỏ qua mọi bản sao liên tiếp** ngay khi đọc. Một wrapper `DistinctCursor` có thể làm việc này và kiểm dữ liệu không giảm theo thứ tự số học.

**Bất biến chính:** trước mỗi vòng lặp, mọi khóa nhỏ hơn min(headA,headB) đã được phân loại đúng và không còn nằm trong phần chưa đọc. Nếu một luồng hết, mọi khóa còn ở luồng kia chỉ có thể xuất trong những toán tử cần khóa xuất hiện một bên.

### 4.1. Union distinct

```text
while A hoặc B còn khóa:
    nếu A nhỏ hơn B hoặc B hết:
        xuất A; tiến A
    ngược lại nếu B nhỏ hơn A hoặc A hết:
        xuất B; tiến B
    ngược lại:  // A == B
        xuất khóa đó một lần
        tiến cả A và B
```

Kết quả được sắp tăng, không có duplicate. Điều này không cần HashSet vì các occurrence bằng nhau đứng cạnh nhau.

### 4.2. Intersection distinct

Khi a<b, bỏ a; khi b<a, bỏ b; khi a=b, xuất một lần rồi tiến cả hai. Nếu một luồng đã hết, không còn khóa giao mới. Có thể dừng sớm để tiết kiệm I/O, **nhưng nếu muốn phát hiện tệp chưa sort ở phần đuôi thì phải đọc tiếp**. Chương trình mẫu chọn kiểm toàn bộ input bằng cách quét hết hai luồng.

### 4.3. A minus B

Khi a<b, xuất a; khi b<a, bỏ b; khi bằng nhau, bỏ cả hai. Nếu B hết, những khóa distinct còn lại của A đều thuộc kết quả. Nếu A hết thì không còn gì để xuất.

### 4.4. Hiệu đối xứng

Xuất khóa khi chỉ có ở đúng một phía. Khi a=b, bỏ cả hai. Một luồng hết thì xuất nốt các khóa distinct của luồng kia.

| Quan hệ head | Union | Intersection | A minus B | Symmetric diff |
|---|---|---|---|---|
| a<b | Xuất a | Không | Xuất a | Xuất a |
| a>b | Xuất b | Không | Không | Xuất b |
| a=b | Xuất a một lần | Xuất a | Không | Không |
| Chỉ A còn | Xuất a | Không | Xuất a | Xuất a |
| Chỉ B còn | Xuất b | Không | Không | Xuất b |

**Đúng đắn:** bởi thứ tự không giảm, không có khóa bé hơn head hiện tại nằm ở phần chưa đọc của luồng. Khi a<b, sự kiện B chứa a đã bị loại trừ; khi a=b, sự hiện diện của cả hai bên được xác nhận. Bảng trên đúng với bốn định nghĩa set, nên theo quy nạp từng khóa được quyết định chính xác một lần.

## 5. Vì sao nối dữ liệu khác giao khóa

Cho hai quan hệ đã sắp theo cột `key`:

```text
L (key,payload):            R (key,payload):
(1,A)                       (1,X)
(1,B)                       (1,Y)
(2,C)                       (3,Z)
(4,D)                       (4,W)
                            (4,V)
```

`INNER JOIN L ON L.key=R.key` tạo:

```text
(1,A,X)
(1,A,Y)
(1,B,X)
(1,B,Y)
(4,D,W)
(4,D,V)
```

Có đúng **6 bản ghi**, do khóa 1 có 2×2 cặp và khóa 4 có 1×2 cặp. Khóa 2 chỉ có ở L và khóa 3 chỉ có ở R nên không xuất.

Với một khóa x, gọi L_x và R_x là toàn bộ các bản ghi của hai luồng mang khóa đó. Bản join phải xuất **tích Descartes L_x×R_x**. Vì các luồng đã sắp, mỗi nhóm khóa đứng liên tiếp, ta có thể nhận diện nhóm bằng cách đọc tới khi khóa đổi.

### 5.1. Chứng minh đúng của sort-merge inner join

Giữ hai head. Nếu left.key < right.key, không có bản ghi phía phải chưa đọc với khóa nhỏ hơn right.key; left hiện tại không còn đối tác, nên được bỏ. Nếu left.key > right.key, bỏ bản ghi phải. Khi bằng nhau tại x, tất cả cặp hợp lệ có khóa x nằm trong L_x×R_x; xuất hết tích đó rồi tiêu thụ cả hai nhóm. Không bản ghi nào với khóa x ở phía sau hai nhóm vì đầu vào đã sort.

Bất biến: toàn bộ cặp join của các khóa nhỏ hơn key đang xét đã được xuất đúng một lần. Bởi thế thuật toán xuất chính xác mọi cặp có khóa bằng nhau, không bỏ và không nhân đôi.

### 5.2. Kích thước kết quả có thể tăng bậc hai

Số dòng join là:

**J = sum_x |L_x| · |R_x|.**

Nếu toàn bộ N_A bản ghi và N_B bản ghi cùng một khóa, J=N_A·N_B. Không thể viết J dòng trong O(N_A+N_B) thời gian khi J lớn, dù thuật toán chỉ quét các tệp nguồn một lượt. Cận đúng phải là **output-sensitive**, thường O(N_A+N_B+J).

Nếu bài chỉ yêu cầu **đếm số cặp** mà không xuất tất cả, có thể quét từng nhóm, đếm a_x,b_x và cộng a_x·b_x. Khi đó không cần spool/cross product và thời gian O(N_A+N_B) với kiểm tràn số đếm.

## 6. Nhóm trùng khóa quá lớn so với RAM

Cách dễ nhất để join một nhóm là giữ toàn bộ nhóm bên phải trong ArrayList, rồi duyệt nhóm này cho từng dòng trái. Nhưng trong external memory, một khóa có thể có hàng triệu dòng; giữ cả nhóm bên phải là **không an toàn về bộ nhớ**.

Một phương pháp **spool** vào tệp tạm:

1. Khi hai head bằng khóa x, ghi **toàn bộ payload nhóm R_x** vào một tệp tạm.
2. Với từng dòng còn lại trong nhóm L_x, mở đọc từ đầu tệp tạm và xuất từng cặp với payload phải.
3. Khi xử lý x xong, đóng/xóa tệp tạm, chuyển sang khóa tiếp theo.
4. Nếu không có nhóm khớp, không tạo tệp tạm.

```text
khi left.key == right.key == x:
    temp = createTemporaryFile()
    while right.key == x:
        temp.append(right.payload)
        right.advance()
    for each leftRow whose key == x:
        for each rightPayload read sequentially from temp:
            emit(x, leftRow.payload, rightPayload)
        left.advance()
    delete temp in finally
```

**Bộ nhớ lõi:** O(1) bản ghi đang nhìn và buffer I/O, không tăng theo số bản ghi của nhóm (vẫn phụ thuộc độ dài dòng lớn nhất). **Dung lượng đĩa tạm:** tối đa kích thước nhóm phải được khớp lớn nhất. Việc ghi nhóm tốn O(|R_x|), đọc lại cho từng dòng trái tốn O(|L_x|·|R_x|), cùng bậc với số dòng kết quả của nhóm.

Có thể tối ưu bằng cách chọn nhóm nhỏ hơn để spool, block nested loop hoặc một thuật toán join khác tùy dữ liệu. Đoạn mã bên dưới chủ động chọn **phía phải** để đơn giản hóa, không tự nhận đã tối ưu mọi tình huống.

Dữ liệu được ghi vào output qua `Writer` ngay khi sinh cặp. `StringWriter` chỉ được dùng trong ví dụ nhỏ để kiểm stdout; nếu dùng StringWriter cho join lớn, output lại bị gom vào RAM và phá ý nghĩa thực tế của external-memory processing.

### 6.1. Quản lý tệp tạm

Dùng `Files.createTempFile`, `try-with-resources` và `finally` để đóng và xóa spool. Nếu hết dung lượng, đọc/ghi thất bại thì báo IOException. Đầu ra đã ghi một phần **không được công nhận là giao dịch hoàn chỉnh**; hệ thống production nên ghi sang file đích tạm và chỉ công bố sau khi toàn bộ thao tác thành công.

Tệp spool có thể chứa dữ liệu nhạy cảm; cần chính sách quyền truy cập, mã hóa/dọn dẹp, quota đĩa và xử lý sự cố tiến trình. Nếu đoạn mã chạy ở môi trường tệp tạm bị chặn, phải chọn cơ chế lưu trữ tạm khác; không được âm thầm bỏ những cặp khớp.

## 7. Độ phức tạp theo CPU, RAM và I/O

| Tác vụ | Thời gian CPU | Bộ nhớ lõi | I/O (mô hình record cố định) |
|---|---|---|---|
| Union DISTINCT 2 luồng | O(N_A+N_B) | O(1) head + buffers | O((N+Z)/B) |
| Intersection DISTINCT | O(N_A+N_B) | O(1) head + buffers | O((N+Z)/B) |
| Difference DISTINCT | O(N_A+N_B) | O(1) head + buffers | O((N+Z)/B) |
| Symmetric difference DISTINCT | O(N_A+N_B) | O(1) head + buffers | O((N+Z)/B) |
| Bag operations theo nhóm | O(N_A+N_B+Z) | O(1) nhóm/counters | O((N+Z)/B) |
| Sort-merge inner join có spool | O(N_A+N_B+J) | O(1) bản ghi + buffers | O((N+J)/B) và overhead spool |
| K-way heap merge, k luồng | O(N log k) | O(k) heads + buffers | O((N+Z)/B) khi đủ buffers |

Các cận trên cho join có thể cộng số thao tác mở/đóng file tạm theo số **nhóm khóa khớp**. Với bản ghi biến độ dài, dùng số **byte**, không chỉ số dòng; overhead hệ tệp và encoding cũng đáng kể.

Một thuật toán có RAM O(1) theo số bản ghi vẫn có thể dùng O(J) dung lượng **output** hoặc tệp tạm O(max |R_x|). Hãy phân biệt rõ **RAM**, **đĩa tạm** và **dữ liệu đầu ra** khi báo cáo.

## 8. K-way merge và external merge sort

Nếu có k tệp/run đã sắp, dùng min-heap chứa một head của mỗi luồng. Lấy khóa nhỏ nhất từ heap, xuất hoặc gom duplicate tùy yêu cầu, đọc head tiếp theo của chính run vừa lấy.

- CPU O(N log k) cho tổng N phần tử.
- RAM O(k) head và k read buffers.
- Khi đủ bộ nhớ để giữ buffers cho k luồng cùng output, mỗi phần tử đọc tuần tự một lần, I/O gần O((N+Z)/B).

Nếu RAM có M đơn vị dữ liệu và mỗi buffer là một block B, fan-in thường cỡ **M/B−1** sau khi dành một buffer output. Không thể merge 1.000 run trong một lượt với chỉ vài buffer mà vẫn lấy cận I/O tối ưu. Phải merge nhiều pass hoặc điều chỉnh chiến lược I/O.

**External merge sort** dùng hai pha: (1) đọc các chunk vừa RAM, sort rồi tạo các run; (2) k-way merge run thành tệp đã sort. Chi phí chuẩn trong mô hình I/O, với M≫B, có dạng gần **O((N/B)(1+log_(M/B)(N/M)))**. Nếu đề nói “dữ liệu đã được sắp xếp”, bài học này chủ yếu giải **pha merge**, không được cộng nhầm hay giấu chi phí sort.

### 8.1. UNION ALL không đơn giản là concatenate

Nếu A=[1,3,5] và B=[2,4], nối trực tiếp A rồi B cho [1,3,5,2,4] **không còn sorted**. UNION ALL vẫn có thể merge hai luồng và giữ mọi occurrence để có [1,2,3,4,5]. Chỉ khi max(A)≤min(B) mới có thể nối file theo đúng thứ tự mà không cần merge.

## 9. Comparator, duplicates, NULL và SQL

Cả hai tệp phải được sắp theo **cùng quan hệ thứ tự mà thuật toán dùng để so head**. Với khóa int, `Integer.compare(a,b)` hoặc phép `<` và `>` là đúng. Không dùng `a-b`: Integer.MAX_VALUE−Integer.MIN_VALUE có thể tràn.

Với khóa String, thứ tự theo UTF-16, Unicode normalization, locale collation và case sensitivity có thể khác nhau. Một bên sort không phân biệt hoa thường và bên kia merge phân biệt hoa thường có thể làm sai kết quả. Với khóa composite (userId,time), phải thống nhất thứ tự các thành phần.

Trong SQL, điều kiện `A.key=B.key` không match NULL theo three-valued logic thông thường; còn điều kiện null-safe có ngữ nghĩa khác. Chương trình Java **không hỗ trợ NULL** và yêu cầu signed int key hợp lệ. Không được tự coi NULL là khóa nguyên 0.

**INNER JOIN** chỉ giữ cặp khớp. **LEFT OUTER JOIN** phải thêm dòng trái không khớp với payload bên phải NULL; **FULL OUTER JOIN** còn giữ bên phải không khớp; **SEMI JOIN** chỉ giữ dòng trái có đối tác; **ANTI JOIN** giữ dòng trái không có đối tác. Cùng framework merge nhưng output semantics khác nhau.

Kết quả join của Java được sắp theo key, với mỗi nhóm in dòng trái theo thứ tự xuất hiện rồi quét nhóm phải theo thứ tự xuất hiện. Trong SQL tổng quát, **không có ORDER BY thì không được dựa vào thứ tự dòng** dù một execution plan cụ thể đang dùng merge join.

## 10. Format đầu vào và hợp đồng Java

Chương trình dùng Java 17, hai định dạng tách biệt:

- Set operations: **mỗi dòng chỉ một số nguyên int**; dòng trống/không hợp lệ bị từ chối; giá trị lặp được phép và tự loại bởi `DistinctCursor`.
- Sort-merge join: mỗi dòng `key<TAB>payload`, đúng một tab; key signed int, payload chuỗi UTF-8 không chứa tab/newline, có thể rỗng.
- Cả hai input phải **không giảm theo giá trị số học**, kể cả khi có số âm, Integer.MIN_VALUE hoặc Integer.MAX_VALUE. Sort theo biểu diễn chuỗi không tương đương sort số: `10` đứng sau `2`.
- API nhận `Reader` và `Writer` để xử lý tuần tự. Core **đóng input**, **flush output** nhưng không tự đóng output; caller quản lý vòng đời Writer.
- Input không sắp sẽ bị phát hiện khi đọc tới dòng giảm. Chương trình cố đọc nốt cả hai luồng, kể cả khi một luồng đã EOF, để kiểm toàn bộ đầu vào.
- Lỗi parse, format hoặc I/O được báo bằng ngoại lệ; không coi output partial là thành công.
- Khi output lớn, tránh StringWriter. Dùng `Files.newBufferedWriter` vào tệp đích độc lập với nguồn, hoặc cơ chế stream có backpressure.

### 10.1. Ví dụ kết nối tệp thực

Đoạn dưới minh họa cách gọi API cho hai file sorted đã có; nó **không phải chương trình độc lập** vì `pathA`, `pathB`, `pathOut` được cung cấp bởi ứng dụng gọi:

```java
try (var a = java.nio.file.Files.newBufferedReader(
            pathA, java.nio.charset.StandardCharsets.UTF_8);
     var b = java.nio.file.Files.newBufferedReader(
            pathB, java.nio.charset.StandardCharsets.UTF_8);
     var out = java.nio.file.Files.newBufferedWriter(
            pathOut, java.nio.charset.StandardCharsets.UTF_8)) {
    ExternalSortedMergeDemo.writeSetOperation(
            a, b, out, ExternalSortedMergeDemo.Operation.UNION);
}
```

Muốn inner join, thay lệnh gọi bằng `ExternalSortedMergeDemo.sortMergeInnerJoin(a,b,out)` và đảm bảo format record với tab. Không viết trực tiếp đè tệp nguồn khi đang đọc nó.

## 11. Khung phép tập hợp có tính đúng và tính kết thúc

Pseudo thuật toán tổng quát cho set DISTINCT:

```text
a = nextDistinct(left)
b = nextDistinct(right)
while a != EOF or b != EOF:
    if a nhỏ hơn b (hoặc b hết):
        xét xuất a theo loại phép toán
        a = nextDistinct(left)
    else if b nhỏ hơn a (hoặc a hết):
        xét xuất b theo loại phép toán
        b = nextDistinct(right)
    else:
        xét xuất một giá trị chung
        a = nextDistinct(left)
        b = nextDistinct(right)
```

**Tính kết thúc:** mỗi bước ít nhất một con trỏ tiến qua một khóa distinct hoặc tới EOF. Tổng khóa distinct hữu hạn nên vòng lặp hữu hạn.

**Không mất khóa:** mọi khóa được xử lý ở bước trở thành head nhỏ nhất của phần chưa phân loại. Vì input sorted, nó không thể quay lại xuất hiện như một khóa mới nhỏ hơn ở phía sau. Thứ tự đầu ra do đó tăng dần.

**Không lặp khóa:** `DistinctCursor` loại duplicate trước khi core emit, và bước a=b emit đúng một lần. Hợp/giao/hiệu theo tập hợp có output chính xác theo định nghĩa.

## 12. Nhận diện lỗi trên dữ liệu có nhiều khóa trùng

Một bản giao sai có thể viết: nếu a=b thì xuất a và tăng i nhưng không tăng j, khiến cùng khóa xuất nhiều lần hoặc vòng lặp lặp vô hạn. Một bản join sai có thể gặp key=7 ở cả hai luồng rồi xuất **một** cặp và tăng cả hai, bỏ hàng nghìn cặp khác của cùng key.

Phải kiểm những lớp case sau:

- Hai file rỗng, một file rỗng, hoặc không có khóa nào chung.
- Mọi dòng đều cùng một khóa.
- Một file có nhiều duplicate, file còn lại chỉ một occurrence.
- Khóa âm và biên int; số lớn không được so bằng phép trừ.
- Phần đuôi file chưa sort dù prefix có vẻ hợp lệ.
- Tệp join thiếu tab, có hai tab hoặc payload chứa ký tự xuống dòng.
- File tạm không ghi được, Writer đích lỗi giữa chừng, output có thể đã ghi dở.
- StringWriter chỉ dành cho test nhỏ; chạy thực trên file cực lớn phải dùng Writer streaming.
- Hai nguồn đang bị thay đổi đồng thời: snapshot không nhất quán có thể làm mất giả thiết sortedness.
- Cùng comparator và cùng null semantics sau serialize/deserialize.

Đối chiếu bằng **TreeSet** cho distinct set ops và **nested-loop** cho join trên dữ liệu nhỏ là một cách kiểm thử độc lập: oracle có cấu trúc khác thuật toán hai con trỏ, giúp phát hiện lỗi điều kiện a<b, b<a và xử lý duplicate.



## 13. Chương trình Java 17 đầy đủ

Lưu mã dưới đây thành `ExternalSortedMergeDemo.java`. `writeSetOperation` xử lý union/giao/hiệu/hiệu đối xứng DISTINCT trên hai tệp số nguyên đã sort. `sortMergeInnerJoin` nhận hai luồng dòng `key<TAB>payload` và tạo các cặp theo khóa bằng nhau, dùng file tạm để giữ bộ nhớ không tăng theo số record của nhóm khóa phải.

```java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public final class ExternalSortedMergeDemo {
    private ExternalSortedMergeDemo() {}

    enum Operation {
        UNION, INTERSECTION, LEFT_MINUS_RIGHT, SYMMETRIC_DIFFERENCE
    }

    static final class DistinctCursor implements AutoCloseable {
        private final BufferedReader in;
        private Integer previousRaw;
        private Integer previousDistinct;
        Integer current;

        DistinctCursor(Reader reader) throws IOException {
            in = new BufferedReader(reader);
            advance();
        }

        void advance() throws IOException {
            String line;
            while ((line = in.readLine()) != null) {
                int value = Integer.parseInt(line);
                if (previousRaw != null && value < previousRaw) {
                    throw new IllegalArgumentException(
                        "input keys not nondecreasing");
                }
                previousRaw = value;
                if (previousDistinct != null
                        && previousDistinct.intValue() == value) {
                    continue;
                }
                previousDistinct = value;
                current = value;
                return;
            }
            current = null;
        }

        @Override public void close() throws IOException { in.close(); }
    }

    private static void emit(BufferedWriter out, int key)
            throws IOException {
        out.write(Integer.toString(key));
        out.newLine();
    }

    // Closes input readers; flushes but does not close output writer.
    static long writeSetOperation(
            Reader leftInput, Reader rightInput,
            Writer output, Operation op) throws IOException {
        Objects.requireNonNull(op, "op");
        try (DistinctCursor a = new DistinctCursor(leftInput);
             DistinctCursor b = new DistinctCursor(rightInput)) {
            BufferedWriter out = new BufferedWriter(output);
            long count = 0;

            // Scan BOTH files completely, including tails.
            while (a.current != null || b.current != null) {
                if (b.current == null
                        || (a.current != null
                            && a.current < b.current)) {
                    if (op == Operation.UNION
                            || op == Operation.LEFT_MINUS_RIGHT
                            || op == Operation.SYMMETRIC_DIFFERENCE) {
                        emit(out, a.current);
                        count++;
                    }
                    a.advance();
                } else if (a.current == null
                        || b.current < a.current) {
                    if (op == Operation.UNION
                            || op == Operation.SYMMETRIC_DIFFERENCE) {
                        emit(out, b.current);
                        count++;
                    }
                    b.advance();
                } else {
                    if (op == Operation.UNION
                            || op == Operation.INTERSECTION) {
                        emit(out, a.current);
                        count++;
                    }
                    a.advance();
                    b.advance();
                }
            }
            out.flush();
            return count;
        }
    }

    record Row(int key, String payload) {}

    static final class RowCursor implements AutoCloseable {
        private final BufferedReader in;
        private Integer previous;
        Row current;

        RowCursor(Reader reader) throws IOException {
            in = new BufferedReader(reader);
            advance();
        }

        void advance() throws IOException {
            String line = in.readLine();
            if (line == null) {
                current = null;
                return;
            }
            int tab = line.indexOf('\t');
            if (tab <= 0 || tab != line.lastIndexOf('\t')) {
                throw new IllegalArgumentException(
                    "expected key<TAB>payload with one TAB");
            }
            int key = Integer.parseInt(line.substring(0, tab));
            if (previous != null && key < previous) {
                throw new IllegalArgumentException(
                    "join input keys not sorted");
            }
            previous = key;
            current = new Row(key, line.substring(tab + 1));
        }

        @Override public void close() throws IOException { in.close(); }
    }

    private static void emitJoin(
            BufferedWriter out, int key, String left, String right)
            throws IOException {
        out.write(Integer.toString(key));
        out.write('\t');
        out.write(left);
        out.write('\t');
        out.write(right);
        out.newLine();
    }

    // One spool file per matching RIGHT group; never buffers whole group.
    static long sortMergeInnerJoin(
            Reader leftInput, Reader rightInput, Writer output)
            throws IOException {
        try (RowCursor a = new RowCursor(leftInput);
             RowCursor b = new RowCursor(rightInput)) {
            BufferedWriter out = new BufferedWriter(output);
            long matches = 0;

            while (a.current != null && b.current != null) {
                int leftKey = a.current.key();
                int rightKey = b.current.key();

                if (leftKey < rightKey) {
                    a.advance();
                    continue;
                }
                if (rightKey < leftKey) {
                    b.advance();
                    continue;
                }

                int key = leftKey;
                Path tmp = Files.createTempFile(
                    "sort-merge-group-", ".tmp");
                try {
                    try (BufferedWriter spool =
                            Files.newBufferedWriter(tmp,
                                StandardCharsets.UTF_8)) {
                        do {
                            spool.write(b.current.payload());
                            spool.newLine();
                            b.advance();
                        } while (b.current != null
                                && b.current.key() == key);
                    }

                    do {
                        String leftValue = a.current.payload();
                        try (BufferedReader spool =
                                Files.newBufferedReader(tmp,
                                    StandardCharsets.UTF_8)) {
                            String rightValue;
                            while ((rightValue = spool.readLine()) != null) {
                                emitJoin(out, key, leftValue, rightValue);
                                matches = Math.addExact(matches, 1);
                            }
                        }
                        a.advance();
                    } while (a.current != null
                            && a.current.key() == key);
                } finally {
                    Files.deleteIfExists(tmp);
                }
            }

            while (a.current != null) a.advance();
            while (b.current != null) b.advance();
            out.flush();
            return matches;
        }
    }

    private static String lines(int[] values) {
        StringBuilder sb = new StringBuilder();
        for (int v : values) sb.append(v).append('\n');
        return sb.toString();
    }

    private static String runSet(
            String a, String b, Operation op) throws IOException {
        StringWriter out = new StringWriter();
        writeSetOperation(new StringReader(a),
            new StringReader(b), out, op);
        return out.toString();
    }

    private static String pretty(String text) {
        String normalized = text.replace("\r\n", "\n").strip();
        if (normalized.isEmpty()) return "[]";
        String[] parts = normalized.split("\n");
        int[] nums = new int[parts.length];
        for (int i = 0; i < parts.length; i++) {
            nums[i] = Integer.parseInt(parts[i]);
        }
        return Arrays.toString(nums);
    }

    private static String rowLines(List<Row> rows) {
        StringBuilder sb = new StringBuilder();
        for (Row row : rows) {
            sb.append(row.key()).append('\t')
                .append(row.payload()).append('\n');
        }
        return sb.toString();
    }

    private static String naiveJoin(
            List<Row> left, List<Row> right) {
        StringBuilder sb = new StringBuilder();
        for (Row l : left) {
            for (Row r : right) {
                if (l.key() == r.key()) {
                    sb.append(l.key()).append('\t')
                        .append(l.payload()).append('\t')
                        .append(r.payload()).append('\n');
                }
            }
        }
        return sb.toString();
    }

    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    public static void main(String[] args) throws IOException {
        String a = "-2\n1\n1\n3\n5\n5\n8\n";
        String b = "-2\n-2\n2\n3\n3\n7\n8\n8\n";
        System.out.println(
            "Union distinct: " + pretty(runSet(a,b,Operation.UNION)));
        System.out.println(
            "Intersection distinct: " +
            pretty(runSet(a,b,Operation.INTERSECTION)));
        System.out.println(
            "A minus B: " +
            pretty(runSet(a,b,Operation.LEFT_MINUS_RIGHT)));
        System.out.println(
            "Symmetric difference: " +
            pretty(runSet(a,b,Operation.SYMMETRIC_DIFFERENCE)));

        String left = "1\tA\n1\tB\n2\tC\n4\tD\n";
        String right = "1\tX\n1\tY\n3\tZ\n4\tW\n4\tV\n";
        StringWriter result = new StringWriter();
        long count = sortMergeInnerJoin(
            new StringReader(left), new StringReader(right), result);
        System.out.println("Inner join rows: " + count);
        System.out.println("Join result: " +
            result.toString().replace("\r\n", "\n").strip()
                .replace('\t', ':').replace("\n", " | "));

        System.out.println("Empty intersection: " +
            runSet("1\n", "2\n", Operation.INTERSECTION).isEmpty());

        boolean rejected = false;
        try {
            runSet("2\n1\n", "", Operation.UNION);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "unsorted input was accepted");
        System.out.println("Unsorted input rejected: " + rejected);

        Random rng = new Random(516L);
        for (int trial = 0; trial < 1_400; trial++) {
            int[] x = new int[rng.nextInt(31)];
            int[] y = new int[rng.nextInt(31)];
            for (int i = 0; i < x.length; i++) x[i] = rng.nextInt(17)-8;
            for (int i = 0; i < y.length; i++) y[i] = rng.nextInt(17)-8;
            Arrays.sort(x);
            Arrays.sort(y);

            TreeSet<Integer> leftSet = new TreeSet<>();
            TreeSet<Integer> rightSet = new TreeSet<>();
            for (int v : x) leftSet.add(v);
            for (int v : y) rightSet.add(v);

            TreeSet<Integer> union = new TreeSet<>(leftSet);
            union.addAll(rightSet);
            TreeSet<Integer> intersect = new TreeSet<>(leftSet);
            intersect.retainAll(rightSet);
            TreeSet<Integer> minus = new TreeSet<>(leftSet);
            minus.removeAll(rightSet);
            TreeSet<Integer> sym = new TreeSet<>(union);
            sym.removeAll(intersect);

            String ls = lines(x), rs = lines(y);
            check(pretty(runSet(ls,rs,Operation.UNION))
                    .equals(union.toString()), "union trial "+trial);
            check(pretty(runSet(ls,rs,Operation.INTERSECTION))
                    .equals(intersect.toString()), "intersect trial "+trial);
            check(pretty(runSet(ls,rs,Operation.LEFT_MINUS_RIGHT))
                    .equals(minus.toString()), "minus trial "+trial);
            check(pretty(runSet(ls,rs,Operation.SYMMETRIC_DIFFERENCE))
                    .equals(sym.toString()), "sym trial "+trial);
        }

        for (int trial = 0; trial < 350; trial++) {
            List<Row> ls = new ArrayList<>();
            List<Row> rs = new ArrayList<>();
            int na = rng.nextInt(21), nb = rng.nextInt(21);
            for (int i = 0; i < na; i++) {
                ls.add(new Row(rng.nextInt(9)-4, "L"+i));
            }
            for (int i = 0; i < nb; i++) {
                rs.add(new Row(rng.nextInt(9)-4, "R"+i));
            }
            ls.sort(Comparator.comparingInt(Row::key));
            rs.sort(Comparator.comparingInt(Row::key));

            StringWriter out = new StringWriter();
            long pairs = sortMergeInnerJoin(
                new StringReader(rowLines(ls)),
                new StringReader(rowLines(rs)), out);
            String expected = naiveJoin(ls,rs);
            String actual = out.toString().replace("\r\n", "\n");
            check(actual.equals(expected), "join trial "+trial);
            check(pairs == expected.chars()
                    .filter(c -> c == '\n').count(), "count trial "+trial);
        }
        System.out.println("Set operations random oracle: 1400 PASS");
        System.out.println("Join random oracle: 350 PASS");
    }
}
```

### 13.1. Biên dịch và chạy

```bash
javac -encoding UTF-8 ExternalSortedMergeDemo.java
java ExternalSortedMergeDemo
```

**Stdout với dữ liệu mẫu và seed trong chương trình:**

```text
Union distinct: [-2, 1, 2, 3, 5, 7, 8]
Intersection distinct: [-2, 3, 8]
A minus B: [1, 5]
Symmetric difference: [1, 2, 5, 7]
Inner join rows: 6
Join result: 1:A:X | 1:A:Y | 1:B:X | 1:B:Y | 4:D:W | 4:D:V
Empty intersection: true
Unsorted input rejected: true
Set operations random oracle: 1400 PASS
Join random oracle: 350 PASS
```

### 13.2. Cách đọc phần quan trọng trong code

**`DistinctCursor`:** đọc từng số nguyên, kiểm giá trị mới không nhỏ hơn `previousRaw` và bỏ occurrence bằng `previousDistinct`. Có thể đọc mọi số âm và các giá trị int biên. Khi tới EOF đặt `current=null`.

**`writeSetOperation`:** ba nhánh a<b, b<a và a=b khớp bảng set semantics. Khi một bên hết, vòng lặp vẫn tiến bên còn lại để kiểm sortedness toàn bộ tệp. `BufferedWriter` được flush nhưng output không bị đóng; chính caller quản lý output.

**`RowCursor`:** parse đúng một tab, kiểm `key` tăng không giảm; payload không có tab/newline và có thể rỗng. Parser tách theo tab, không dựa vào trim để không âm thầm thay đổi payload.

**`sortMergeInnerJoin`:** với matching key, ghi nhóm phải vào file tạm. Mỗi dòng trái quét lại file tạm và xuất tất cả cặp. `finally` xóa tệp tạm kể cả khi phát sinh lỗi. `matches` dùng long và `Math.addExact` để phát hiện overflow số cặp.

**Oracle:** `TreeSet` tự tính bốn phép tập hợp trên input nhỏ; nested loops tự tính join cặp bản ghi. Hai oracle độc lập về logic với merge pointers, giúp bắt lỗi duplicate, EOF và điều kiện so sánh.

Chương trình kiểm **1.400 cặp luồng khóa ngẫu nhiên** với bốn phép toán, và **350 cặp quan hệ ngẫu nhiên** với nested-loop oracle. Test nhỏ dùng StringReader/StringWriter để so kết quả byte/dòng; production dùng buffered file readers/writers, không materialize toàn bộ dữ liệu.

### 13.3. Điều kiện giới hạn của demo

Chương trình không tự sort input, không làm outer join, không xử lý NULL, không parse CSV/TSV có quoting/escaping phức tạp, không cung cấp atomic write và không giới hạn độ dài một dòng. Để dùng production, bổ sung validation kích thước, kiểm comparator/collation, quota tệp tạm, an toàn đầu ra khi IOException và giám sát thời gian xử lý những nhóm khóa sinh sản phẩm Descartes cực lớn.

## 14. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nạp toàn bộ hai file vào HashSet | RAM không đủ | Sequential merge trên dữ liệu sorted |
| Dùng hai con trỏ khi input chưa sort | Bỏ sót hoặc sai thứ tự | Sort ngoài bộ nhớ hoặc đổi thuật toán |
| Nhầm DISTINCT với ALL | Kết quả thiếu/thừa occurrence | Xác định bag/set trước khi code |
| Giao distinct xuất một khóa nhiều lần | Sai semantics | Bỏ các duplicate liền nhau |
| Khi a=b chỉ tăng một con trỏ | Lặp kết quả hoặc vòng không dừng | Xử lý rồi tăng cả hai |
| Join a=b chỉ xuất một cặp | Bỏ các cặp trong nhóm trùng khóa | Xuất tích Descartes nhóm |
| Cho rằng join luôn O(N_A+N_B) | Quên J có thể bậc hai | Tính O(N_A+N_B+J) |
| Dồn một nhóm khóa lớn vào List | Tràn RAM | Spool ra tệp tạm |
| Quên xóa spool khi IOException | Rò rỉ ổ đĩa | try-with-resources + finally |
| Không tính output I/O | Ước lượng sai throughput | Tính Z/B hoặc J/B |
| So int bằng phép trừ | Overflow | Integer.compare |
| Hai file dùng comparator khác | Mất bất biến merge | Đồng nhất sort/equality |
| Không kiểm tail khi intersection kết thúc | Có thể bỏ qua dữ liệu lỗi | Drain cả hai trong strict mode |
| Coi SQL JOIN tự bảo đảm ORDER BY | Thứ tự tùy plan | ORDER BY nếu cần |
| Coi NULL như một int | Sai three-valued logic | Quy định null policy |
| Ghi trực tiếp lên file nguồn | Làm hỏng input đang đọc | Output ra file khác |
| Xem output partial là thành công | Mất dữ liệu | Atomic publish/rollback |
| Dùng StringWriter cho output rất lớn | Giữ toàn bộ kết quả trong RAM | Streaming Writer |
| Xem B records/block cho dòng bất kỳ | Bỏ qua kích thước biến đổi | Đo byte và record max size |
| Tạo k-way merge nhiều run hơn buffer | Hiệu năng I/O tệ | Giới hạn fan-in, nhiều pass |
| Bỏ qua tệp temp chứa dữ liệu nhạy cảm | Lộ thông tin | Quyền/erase/encryption phù hợp |

## 15. Bài tập có đáp án

**Bài 1.** Vì sao sorted input cho phép giao hai tập trong O(N)? *Đáp án:* hai head chỉ tăng và mỗi dòng được đọc một lượt.

**Bài 2.** Khi a<b trong intersection, tiến phía nào? *Đáp án:* A, vì B chưa đọc chỉ chứa giá trị ≥b>a.

**Bài 3.** A=[1,1,3], B=[1,2,3,3]. UNION DISTINCT? *Đáp án:* [1,2,3].

**Bài 4.** Với cùng dữ liệu, INTERSECTION DISTINCT? *Đáp án:* [1,3].

**Bài 5.** A MINUS B DISTINCT? *Đáp án:* rỗng.

**Bài 6.** B MINUS A DISTINCT? *Đáp án:* [2].

**Bài 7.** A △ B DISTINCT? *Đáp án:* [2].

**Bài 8.** Cùng khóa x có c_A=4,c_B=3. UNION ALL có bao nhiêu? *Đáp án:* 7 occurrence.

**Bài 9.** INTERSECT ALL? *Đáp án:* min(4,3)=3 occurrence.

**Bài 10.** A EXCEPT ALL B? *Đáp án:* 1 occurrence.

**Bài 11.** Cùng khóa, A có hai dòng, B có ba dòng. INNER JOIN có bao nhiêu dòng? *Đáp án:* 6.

**Bài 12.** Join có thể nhiều hơn input không? *Đáp án:* có, tối đa N_A·N_B khi mọi khóa giống nhau.

**Bài 13.** Vì sao không thể in J dòng trong O(N) nếu J rất lớn? *Đáp án:* riêng ghi output đã có lower bound Ω(J).

**Bài 14.** Với B record/block, đọc N input tuần tự tốn khoảng bao nhiêu I/O? *Đáp án:* O(ceil(N/B)).

**Bài 15.** Vì sao cần thêm Z/B vào chi phí I/O? *Đáp án:* phải ghi kết quả ra đĩa/stream.

**Bài 16.** Khi một nhóm join quá RAM, chiến lược ví dụ? *Đáp án:* spool nhóm phải vào tệp tạm rồi đọc lại.

**Bài 17.** Bộ nhớ lõi của spool join lớn theo nhóm không? *Đáp án:* không theo số dòng nhóm; cần buffer và giới hạn độ dài mỗi dòng.

**Bài 18.** Dung lượng spool tối đa phụ thuộc gì? *Đáp án:* nhóm phải lớn nhất được khớp.

**Bài 19.** Có cần spool nếu hai head không khớp? *Đáp án:* không.

**Bài 20.** Nếu chỉ cần count pairs cho join, cách làm? *Đáp án:* đếm số dòng a_x,b_x theo nhóm và cộng a_x·b_x.

**Bài 21.** Sort-merge join hỗ trợ trực tiếp outer join trong demo? *Đáp án:* không, mã chỉ inner join.

**Bài 22.** SQL JOIN có bảo đảm thứ tự output nếu không ORDER BY? *Đáp án:* không.

**Bài 23.** Tại sao không so int bằng a−b? *Đáp án:* có thể tràn số.

**Bài 24.** Nếu một tệp sort từ điển String và một tệp sort số, merge có đúng không? *Đáp án:* không, comparator không thống nhất.

**Bài 25.** Trong SQL, NULL có match phép bằng thông thường không? *Đáp án:* không, kết quả UNKNOWN.

**Bài 26.** Thời gian k-way heap merge của N dòng, k run? *Đáp án:* O(N log k).

**Bài 27.** Cần bao nhiêu head cho k-way merge? *Đáp án:* O(k).

**Bài 28.** Nếu không đủ buffer cho k run trong RAM, làm gì? *Đáp án:* giảm fan-in và merge qua nhiều pass.

**Bài 29.** UNION ALL bằng concatenation luôn sorted không? *Đáp án:* không; cần max(A)≤min(B) hoặc merge.

**Bài 30.** Vì sao tệp chưa sorted phải trả lỗi? *Đáp án:* các lập luận bỏ qua khóa nhỏ hơn sẽ không còn đúng.

**Bài 31.** Vì sao dùng TreeSet làm oracle distinct? *Đáp án:* độc lập với thuật toán pointer merge và xử lý membership đúng.

**Bài 32.** Vì sao nested loops làm oracle join? *Đáp án:* liệt kê mọi cặp, độc lập với xử lý theo nhóm.

**Bài 33.** StringWriter dùng trong demo có áp dụng trực tiếp cho join rất lớn không? *Đáp án:* không, nó tích lũy kết quả trong RAM.

**Bài 34.** Nếu temp file hết quota, có được coi join hoàn thành? *Đáp án:* không, báo IOException và xử lý output chưa hoàn chỉnh.

**Bài 35.** Dữ liệu có payload chứa tab/newline nên làm gì? *Đáp án:* dùng định dạng có escaping/quoting hoặc parser phù hợp.

**Bài 36.** Vì sao các bản ghi phải được sort theo cùng null/collation policy? *Đáp án:* để head comparison phản ánh đúng equality và thứ tự của join.

## 16. Checklist và kết luận

Kiểm tra điều kiện sorted input; xác định DISTINCT/ALL và kiểu join; thống nhất comparator, encoding và chính sách NULL; xử lý duplicate theo đúng toán tử; lập kế hoạch dung lượng tệp tạm và output; kiểm tra số khối I/O, số record tối đa và k-way buffer; đảm bảo tài nguyên đóng đúng, kết quả lỗi không được publish như hoàn chỉnh; dùng oracle trên các ca rỗng, trùng khóa, khóa âm và input chưa sorted.

**Hợp và giao trên hai luồng đã sắp** chỉ cần tiến các con trỏ đọc tuần tự, với O(N_A+N_B) thời gian, bộ nhớ nhỏ và chi phí I/O tuyến tính theo số khối. **Sort-merge join** cũng tận dụng thứ tự nhưng phải xuất đủ mọi cặp của các nhóm khóa bằng nhau; số dòng kết quả J có thể rất lớn, nên cận đúng phải cộng chi phí O(J). Spool tệp tạm giúp giữ nhóm khóa lớn khỏi RAM, đổi lại cần quản lý thêm I/O và vòng đời tệp. Trong mọi trường hợp, **ngữ nghĩa duplicate và điều kiện sorted** quyết định tính đúng trước cả tối ưu hiệu năng.
