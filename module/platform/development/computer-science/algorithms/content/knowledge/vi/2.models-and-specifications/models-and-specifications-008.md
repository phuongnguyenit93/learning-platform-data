# Giả mã và cách diễn đạt độc lập với ngôn ngữ lập trình

**Giả mã (pseudocode)** là cách diễn đạt các bước của một thuật toán bằng ngôn ngữ gần với lời nói thông thường, kết hợp cấu trúc logic quen thuộc như gán, rẽ nhánh, vòng lặp và lời gọi hàm. Mục tiêu là để người đọc hiểu **thuật toán làm gì và diễn ra như thế nào**, trước khi quyết định cài đặt bằng Java, Python, C++ hay ngôn ngữ khác.

Một bản giả mã tốt có thể được người khác chuyển thành chương trình, diễn giải bằng tay, đánh giá tính đúng đắn và ước lượng độ phức tạp. Giả mã **không phải** ngôn ngữ lập trình có chuẩn cú pháp chung: các sách, nhóm và môn học có thể dùng những quy ước khác nhau, miễn là chúng được định nghĩa và dùng nhất quán.

## 1. “Độc lập với ngôn ngữ lập trình” nghĩa là gì?

Giả mã mô tả logic của thuật toán mà không gắn với cú pháp, thư viện, kiểu dữ liệu cụ thể hoặc cơ chế chạy của một ngôn ngữ. Ví dụ, yêu cầu “lặp qua từng phần tử và đếm những số dương” có thể dùng một vòng lặp trong Java, Python hoặc C++. Điều cốt lõi là **trạng thái nào được xét, điều kiện nào được kiểm tra, kết quả được cập nhật ra sao**, chứ không phải dấu ngoặc nhọn hay tên hàm có sẵn.

Tuy nhiên, độc lập với ngôn ngữ **không có nghĩa là mơ hồ**. Người viết vẫn phải làm rõ:

- Miền đầu vào, điều kiện hợp lệ và ý nghĩa của đầu ra.
- Kiểu dữ liệu ở mức khái niệm (số nguyên, dãy, tập hợp, đồ thị…), quy ước chỉ số mảng và phép toán.
- Thứ tự thực hiện, điều kiện nhánh, cập nhật biến và điều kiện dừng.
- Hành vi ở tình huống biên, chẳng hạn mảng rỗng hay không tìm được kết quả.

Giả mã cũng khác **đặc tả**: đặc tả phát biểu thuật toán **phải thỏa yêu cầu nào**, còn giả mã đề xuất **cách thực hiện** để đáp ứng yêu cầu ấy. Hai bản cài đặt có thể có cú pháp hoàn toàn khác nhưng cùng hiện thực một giả mã, hoặc có các bước khác nhau mà vẫn thỏa một đặc tả.

## 2. Các quy ước thường dùng

Đây là một bộ ký hiệu minh họa, **không phải bộ cú pháp bắt buộc** cho mọi tài liệu. Khi viết, chọn một bộ quy ước rồi sử dụng nhất quán.

| Ý nghĩa | Ký hiệu giả mã thường gặp | Lưu ý |
| --- | --- | --- |
| Gán giá trị | `x ← 5` hoặc `x := 5` | Thay đổi biến `x`; khác với phép so sánh. |
| So sánh bằng | `x = 5` | Biểu thức đúng/sai, không phải lệnh gán. |
| So sánh khác | `x ≠ 5` | Có tài liệu viết `x != 5`. |
| Quan hệ | `<`, `≤`, `>`, `≥` | Nêu rõ ý nghĩa các biên được tính hay loại trừ. |
| Logic | `AND`, `OR`, `NOT` | Dùng để kết hợp hoặc đảo điều kiện. |
| Chia lấy dư | `a MOD b` | Với ví dụ trong bài, `a ≥ 0` và `b > 0`. |
| Rẽ nhánh | `IF ... THEN ... ELSE ... END IF` | Có thể bỏ `ELSE` nếu không cần. |
| Lặp có điều kiện | `WHILE ... DO ... END WHILE` | Kiểm tra điều kiện trước mỗi lượt. |
| Lặp theo chỉ số | `FOR i FROM ... TO ... DO` | Phải xác định bước nhảy và biên cuối. |
| Trả kết quả | `RETURN value` | Kết thúc lời gọi thuật toán/hàm hiện tại. |
| Chú thích | `// giải thích` | Phục vụ người đọc, không phải bước tính toán. |

Có thể dùng **thụt lề** để biểu thị khối lệnh, hoặc dùng các từ khóa kết thúc như `END IF` và `END WHILE`. Nếu dùng cả hai, chúng phải thống nhất. Một câu như “xử lý mảng theo cách thích hợp” là chưa đủ chính xác để coi là một bước giả mã.

Các quy ước cần công bố khi thích hợp:

- **Chỉ số:** trong các ví dụ của bài, phần tử đầu tiên là `A[0]`, phần tử cuối là `A[LENGTH(A) - 1]`.
- **Vòng FOR:** nếu viết `FOR i FROM 0 TO n - 1`, biên `n - 1` được tính; khi `n = 0`, vòng lặp chạy **0 lần**.
- **Số nguyên:** có thể giả định số nguyên toán học hoặc số nguyên hữu hạn của máy; khi cài đặt phải chú ý tràn số, độ chính xác và phép chia.
- **Tham số và dữ liệu:** nếu thuật toán thay đổi trực tiếp mảng hay cấu trúc đầu vào thì phải nói rõ.

## 3. Cách viết một bản giả mã có thể kiểm tra

Một cách trình bày hữu ích là bắt đầu bằng **hợp đồng thuật toán**, tiếp theo là các bước và cuối cùng là lý do các bước này hợp lệ:

1. **Tên và mục tiêu:** thuật toán cần giải bài toán cụ thể nào?
2. **INPUT / tiền điều kiện:** dữ liệu nào được cung cấp, những đầu vào nào hợp lệ?
3. **OUTPUT / hậu điều kiện:** kết quả phải có ý nghĩa chính xác gì?
4. **Các bước:** biến trạng thái, phép gán, kiểm tra, nhánh và vòng lặp theo đúng thứ tự.
5. **Điều kiện kết thúc:** đường nào đưa đến `RETURN`, và điều gì bảo đảm tiến triển?
6. **Kiểm chứng:** chạy thử bằng tay, phân tích tính đúng, trường hợp biên và chi phí.

Ví dụ đặc tả cho thuật toán **ước chung lớn nhất (ƯCLN)**:

- **Input:** hai số nguyên `a`, `b` không âm và không đồng thời bằng `0`.
- **Output:** số nguyên dương lớn nhất chia hết cả `a` và `b`; ký hiệu `gcd(a,b)`.
- **Không cần:** bàn phím, câu lệnh in ra màn hình, cấu trúc class hay thư viện cụ thể.

Từ cùng đặc tả này, ta có thể chọn thuật toán Euclid, liệt kê các ước số hoặc cách khác. Giả mã là chỗ diễn đạt **phương án thuật toán đã chọn**.

## 4. Ví dụ hoàn chỉnh: thuật toán Euclid tìm ƯCLN

Quan sát toán học trung tâm là: với `a ≥ 0` và `b > 0`, `gcd(a,b) = gcd(b, a MOD b)`. Ta có thể thay cặp `(a,b)` bằng `(b,r)`, trong đó `r` là số dư, mà không đổi ƯCLN.

### Giả mã

```text
ALGORITHM GCD_EUCLID(a, b)
    PRECONDITION:
        a, b là số nguyên
        a >= 0 AND b >= 0
        NOT (a = 0 AND b = 0)
    POSTCONDITION:
        RETURN gcd(a ban đầu, b ban đầu), là số nguyên dương

    WHILE b != 0 DO
        r <- a MOD b
        a <- b
        b <- r
    END WHILE

    RETURN a
END ALGORITHM
```

**Cách đọc:** khi `b` còn khác `0`, tính số dư `r`; đưa `b` cũ sang `a`, rồi đưa `r` sang `b`. Khi `b = 0`, `a` là kết quả. Dùng biến tạm `r` giúp tránh sự mơ hồ của phép gán đồng thời. Trong ký hiệu đang dùng, `a <- b` là gán; `a = b` là so sánh.

Các từ `PRECONDITION`, `POSTCONDITION`, `ALGORITHM` và `END ALGORITHM` là nhãn trình bày để đọc cho rõ; chúng không được một trình thông dịch giả mã chung tự động thực thi.

### Mô phỏng bằng tay

Đầu vào `a = 48`, `b = 18`:

| Lượt | `a` trước lượt | `b` trước lượt | `r = a MOD b` | `(a,b)` sau lượt |
| --- | ---: | ---: | ---: | --- |
| 1 | 48 | 18 | 12 | `(18, 12)` |
| 2 | 18 | 12 | 6 | `(12, 6)` |
| 3 | 12 | 6 | 0 | `(6, 0)` |

Vì `b = 0`, vòng `WHILE` kết thúc và thuật toán trả `6`. Mỗi cặp `(a,b)` trong bảng có cùng ƯCLN. Với `(15,0)`, vòng lặp không chạy lần nào và trả `15`; với `(0,7)`, chạy một lượt rồi trả `7`. Cặp `(0,0)` bị loại ngay trong tiền điều kiện vì không có ƯCLN dương lớn nhất theo định nghĩa đã chọn.

### Vì sao thuật toán đúng và chắc chắn dừng?

**Bất biến vòng lặp:** ở đầu mỗi lượt, ƯCLN của cặp biến hiện tại bằng ƯCLN của cặp đầu vào ban đầu. Điều này đúng trước lượt đầu; phép thay `(a,b)` thành `(b, a MOD b)` giữ nó đúng sau mỗi lượt. Khi kết thúc với `b = 0`, ta có `gcd(a,0) = a` cho `a > 0`; kết hợp bất biến suy ra `a` trả về chính là ƯCLN cần tìm.

**Tính kết thúc:** trong một lượt có `b > 0`, số dư luôn thỏa `0 ≤ a MOD b < b`. Vì thế giá trị `b` mới là số nguyên không âm **nhỏ hơn** `b` cũ. Một dãy số nguyên không âm giảm nghiêm ngặt không thể kéo dài mãi; cuối cùng `b = 0`. Không được bỏ qua điều kiện `b != 0` vì phép `MOD 0` không xác định.

Với mô hình tính toán xem phép chia lấy dư trên số nguyên có chi phí hằng số, thuật toán Euclid dùng **O(log(max(a,b) + 1))** lượt chia lấy dư trong trường hợp tổng quát và chỉ cần **O(1)** biến phụ. Phân tích chi phí theo bit của các phép toán trên số rất lớn cần mô hình chi phí chi tiết hơn.

## 5. Từ giả mã sang Java 17+

Giả mã ở trên là mô tả thiết kế; đoạn dưới là **chương trình Java hoàn chỉnh có thể biên dịch và chạy**. Đặt tên tệp `EuclidDemo.java`:

```java
public class EuclidDemo {
    public static int gcd(int a, int b) {
        if (a < 0 || b < 0 || (a == 0 && b == 0)) {
            throw new IllegalArgumentException(
                    "a and b must be non-negative and not both zero");
        }

        while (b != 0) {
            int r = a % b;
            a = b;
            b = r;
        }

        return a;
    }

    public static void main(String[] args) {
        System.out.println(gcd(48, 18));
        System.out.println(gcd(15, 0));
        System.out.println(gcd(0, 7));
        System.out.println(gcd(17, 13));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac EuclidDemo.java
java EuclidDemo
```

Kết quả hiển thị chính xác:

```text
6
15
7
1
```

| Ý tưởng trong giả mã | Biểu thức Java | Phần logic giữ nguyên |
| --- | --- | --- |
| `WHILE b != 0 DO` | `while (b != 0) {` | Tiếp tục khi số thứ hai khác 0. |
| `r <- a MOD b` | `int r = a % b;` | Tính số dư trước khi cập nhật `a` và `b`. |
| `a <- b` | `a = b;` | Đưa giá trị `b` hiện tại vào `a`. |
| `b <- r` | `b = r;` | Đưa số dư vào `b`. |
| `RETURN a` | `return a;` | Trả kết quả và kết thúc phương thức. |

Phần `public class`, `static`, dấu chấm phẩy, dấu ngoặc nhọn và cú pháp xử lý lỗi thuộc về **cài đặt Java**. Chúng không làm thay đổi chứng minh toán học của thuật toán. Ngược lại, khi chuyển sang ngôn ngữ khác, phải giữ nguyên **thứ tự cập nhật biến** và ý nghĩa phép lấy dư; đổi thứ tự gán có thể làm thuật toán sai.

Để phù hợp đặc tả, chương trình kiểm tra tiền điều kiện và ném ngoại lệ khi `a` hoặc `b` âm, hoặc cả hai bằng `0`. Mã Java dùng `int`; đối với dữ liệu lớn hơn miền `int`, người cài đặt phải chọn kiểu biểu diễn thích hợp. Trong chương trình này, `System.out.println` chỉ trình bày kết quả để kiểm tra; thuật toán thực sự trả kết quả ở lệnh `return`.

## 6. Ví dụ khác: duyệt dãy mà không lệ thuộc vòng lặp của ngôn ngữ

Để thấy giả mã áp dụng được cho cả dữ liệu dạng dãy, xét bài toán **đếm số phần tử dương**.

**Input:** mảng `A` gồm `n` số nguyên, có thể rỗng; `n = LENGTH(A)`. **Output:** số phần tử `A[i] > 0` với chỉ số từ `0` đến `n - 1`. Mảng đầu vào không bị sửa.

```text
ALGORITHM COUNT_POSITIVE(A)
    count <- 0

    FOR i FROM 0 TO LENGTH(A) - 1 DO
        IF A[i] > 0 THEN
            count <- count + 1
        END IF
    END FOR

    RETURN count
END ALGORITHM
```

Ở đây quy ước vòng `FOR` tăng `i` thêm `1` sau mỗi lượt, có tính biên cuối `LENGTH(A)-1`, và không chạy nếu cận đầu lớn hơn cận cuối. Ví dụ `A = [0, -2, 5, 3]` cho kết quả `2`. Với `A = []`, vòng lặp có `0` lượt, nên trả `0`. Không cần dùng cú pháp `for (int i = 0; ...)` của Java mới diễn đạt được ý tưởng.

Một cách viết tương đương về logic là:

```text
ALGORITHM COUNT_POSITIVE_WHILE(A)
    count <- 0
    i <- 0
    WHILE i < LENGTH(A) DO
        IF A[i] > 0 THEN
            count <- count + 1
        END IF
        i <- i + 1
    END WHILE
    RETURN count
END ALGORITHM
```

Hai phiên bản cùng trả kết quả vì chúng xét đúng các chỉ số `0, 1, ..., n-1` theo thứ tự và tăng `count` đúng một lần cho mỗi số dương. Trước khi kiểm tra phần tử `A[i]`, `count` bằng số phần tử dương trong đoạn `A[0..i-1]` đã xét. Khi `i = n`, bất biến này bảo đảm kết quả cuối cùng đúng. Điều kiện `i < n` cùng bước `i <- i + 1` bảo đảm vòng `WHILE` dừng. Chi phí thời gian là **O(n)**, bộ nhớ phụ **O(1)**.

So sánh hai cách viết cho thấy: **khác cấu trúc trình bày vẫn có thể mô tả cùng một thuật toán**. Nhưng nếu phiên bản `WHILE` quên tăng `i`, ý nghĩa và tính kết thúc sẽ thay đổi ngay.

## 7. Giả mã so với các cách biểu diễn thuật toán khác

| Cách biểu diễn | Ưu điểm | Giới hạn thường gặp | Phù hợp khi |
| --- | --- | --- | --- |
| Mô tả bằng ngôn ngữ tự nhiên | Dễ tiếp cận, giải thích mục tiêu và ý nghĩa | Có thể mơ hồ về thứ tự hoặc điều kiện | Giới thiệu bài toán, giải thích trực giác. |
| **Giả mã** | Thể hiện logic tuần tự, nhánh, lặp rõ và ít phụ thuộc cú pháp | Không có chuẩn thống nhất để tự chạy | Thiết kế, phản biện, dạy học, chuyển sang nhiều ngôn ngữ. |
| Lưu đồ | Trực quan các đường đi và quyết định | Khó đọc khi thuật toán có nhiều nhánh hoặc cấu trúc lớn | Trình bày luồng xử lý ngắn, giải thích các nhánh. |
| Mã nguồn Java/Python/... | Có thể biên dịch/chạy, dùng kiểu và thư viện thật | Phụ thuộc quy tắc và môi trường ngôn ngữ | Cài đặt, kiểm thử và triển khai. |
| Đặc tả hình thức | Phát biểu yêu cầu, bất biến hay tính chất chính xác | Đòi hỏi ký hiệu và phương pháp chứng minh | Hệ thống cần chứng minh tính đúng đắn nghiêm ngặt. |

Không phải lúc nào cũng cần lập đủ năm dạng. Với thuật toán ngắn, hợp đồng đầu vào/đầu ra và vài dòng giả mã rõ ràng có thể đủ để cả nhóm hiểu cách làm trước khi viết mã.

**Cách chuyển đổi có kiểm soát:** giữ nguyên tiền điều kiện và hậu điều kiện, xác định mỗi biến được biểu diễn bằng kiểu nào, chuyển chính xác ranh giới của vòng lặp, rồi kiểm thử cùng một bộ trường hợp ở các bản cài đặt. Nếu ngôn ngữ đích có tràn số, phép chia nguyên, so sánh số thực hoặc chuỗi theo quy tắc khác, cần điều chỉnh biểu diễn và chứng minh tính tương ứng với đặc tả.

## 8. Sai lầm phổ biến khi viết giả mã

- **Viết câu lệnh mơ hồ:** “sắp xếp nhanh” hay “xử lý phần tử phù hợp” chưa mô tả chính xác thuật toán làm gì. Cần nêu phép so sánh, cập nhật và cách chọn bước tiếp theo.
- **Lẫn gán và so sánh:** `x <- y` thay đổi trạng thái; `x = y` kiểm tra quan hệ. Dùng một ký hiệu cho cả hai mà không giải thích dễ gây hiểu nhầm.
- **Không quy định chỉ số mảng:** cùng một thuật toán nhưng một tài liệu bắt đầu ở 0, tài liệu khác bắt đầu ở 1 có thể gây lỗi lệch một vị trí.
- **Không chỉ rõ cận vòng lặp:** `FOR i FROM 1 TO n` phải xác định có lấy `n` hay không, bước tăng giảm là bao nhiêu và trường hợp miền rỗng.
- **Cập nhật biến sai thứ tự:** với Euclid, nếu gán `a <- b` trước khi tính `r <- a MOD b`, giá trị `a` cũ đã mất và số dư tính sai.
- **Không có tiến triển:** vòng `WHILE` giữ nguyên điều kiện đúng mãi sẽ không kết thúc.
- **Thiếu quy tắc khi đầu vào không hợp lệ:** `MOD 0`, truy cập mảng rỗng hoặc sử dụng dữ liệu chưa khởi tạo đều cần được xử lý bằng tiền điều kiện hoặc nhánh kiểm tra.
- **Lẫn `PRINT` với `RETURN`:** in ra kết quả không tự động cung cấp giá trị cho thuật toán gọi. Ghi rõ đầu ra là giá trị trả về, dữ liệu biến đổi hay tác động bên ngoài.
- **Bê nguyên cú pháp ngôn ngữ đích:** một đoạn đầy `System.out.println`, `Scanner` và kiểu lớp Java có thể chạy được nhưng khó xem là diễn đạt độc lập với ngôn ngữ; chỉ nêu cơ chế cài đặt khi cần.
- **Bỏ qua chi phí thực tế của phép toán:** giả mã có thể coi số nguyên là không giới hạn, trong khi cài đặt dùng kiểu hữu hạn. Khi dữ liệu có thể lớn, phải nói rõ mô hình chi phí và biểu diễn.

## 9. Danh sách tự rà soát khi hoàn thành giả mã

Trước khi chuyển giả mã thành chương trình, hãy trả lời lần lượt:

1. Người chưa biết Java hoặc Python có hiểu đầu vào, kết quả và thứ tự các bước không?
2. Các ký hiệu gán, so sánh, chia lấy dư, ranh giới mảng và vòng lặp đã có quy ước rõ chưa?
3. Có đầu vào biên nào khiến một phép toán không xác định, nhánh không xử lý hoặc vòng lặp sai không?
4. Mỗi nhánh có thể đi đến đâu; thuật toán có trả về đúng đầu ra trên tất cả đầu vào hợp lệ không?
5. Với mỗi vòng lặp, có thể mô tả biến hoặc đại lượng **tiến triển đến điều kiện dừng** không?
6. Có thể mô phỏng từng dòng giả mã bằng một ví dụ bình thường và một trường hợp biên không?
7. Sau khi cài đặt ở ngôn ngữ cụ thể, kiểu dữ liệu và ngữ nghĩa phép toán có còn phù hợp với đặc tả không?

## 10. Bài tự luyện có lời giải

**Bài 1.** Với giả mã Euclid, hãy mô phỏng `GCD_EUCLID(21, 14)`. **Lời giải:** `21 MOD 14 = 7`, chuyển `(a,b)` thành `(14,7)`; tiếp theo `14 MOD 7 = 0`, chuyển thành `(7,0)`; trả `7`. Đại lượng `b` giảm từ 14 xuống 7 rồi 0.

**Bài 2.** Giả mã đếm số dương trả gì với `A = [-3, 0, 4, 1]` và `A = []`? **Lời giải:** lần lượt trả `2` và `0`; số 0 không phải số dương và mảng rỗng không có phần tử để duyệt.

**Bài 3.** Một người sửa vòng lặp `COUNT_POSITIVE_WHILE` thành `WHILE i <= LENGTH(A) DO`. Điều gì sai? **Lời giải:** khi `i = LENGTH(A)`, thuật toán cố truy cập `A[i]` bên ngoài phạm vi hợp lệ nếu vẫn dùng thân vòng lặp như cũ. Cận đúng là `i < LENGTH(A)`.

**Bài 4.** Có thể thay `RETURN a` trong Euclid bằng “in `a`” không? **Lời giải:** nếu đặc tả yêu cầu giá trị trả về cho nơi gọi, thì không; việc in ra chỉ tạo tác động hiển thị. Muốn đổi cách xuất kết quả phải thay đổi đặc tả và cách tương tác với thuật toán gọi.

**Bài 5.** Hãy viết giả mã tìm giá trị lớn nhất trong một mảng số nguyên **không rỗng**. Một lời giải:

```text
ALGORITHM MAX_VALUE(A)
    PRECONDITION: LENGTH(A) >= 1
    best <- A[0]
    FOR i FROM 1 TO LENGTH(A) - 1 DO
        IF A[i] > best THEN
            best <- A[i]
        END IF
    END FOR
    RETURN best
END ALGORITHM
```

Bất biến: sau khi xử lý `A[0..i]`, `best` là giá trị lớn nhất trong đoạn đã xét. Khi `A` có đúng một phần tử, vòng lặp chạy 0 lần và trả phần tử ấy. Điều này cũng minh họa vì sao **tiền điều kiện mảng không rỗng** cần được công bố: nếu cho phép mảng rỗng, dòng `best <- A[0]` sẽ không hợp lệ.

Giả mã có ích nhất khi người đọc có thể **mô phỏng, kiểm chứng và cài đặt lại** mà không phải đoán ý người viết. Độc lập với ngôn ngữ là độc lập với cú pháp cài đặt, còn logic và hợp đồng của thuật toán phải đủ chính xác để kiểm tra.