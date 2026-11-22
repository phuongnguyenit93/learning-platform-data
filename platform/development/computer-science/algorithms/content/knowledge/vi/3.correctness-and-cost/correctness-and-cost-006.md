# Phân biệt đúng bộ phận với đúng toàn phần

## 1. Bài toán: kết quả đúng liệu đã đủ?

Khi đánh giá tính đúng của thuật toán, hai câu hỏi cần được trả lời **riêng biệt**:

1. **Nếu thuật toán kết thúc, kết quả có thỏa đặc tả không?** Đây là câu hỏi về **tính đúng bộ phận (partial correctness)**.
2. **Thuật toán có chắc chắn kết thúc với mọi đầu vào hợp lệ không?** Khi kết hợp câu trả lời có với tính đúng bộ phận, ta có **tính đúng toàn phần (total correctness)**.

Một chương trình có thể không bao giờ đưa ra kết quả sai đơn giản vì nó **không bao giờ trả về**. Vì vậy, chứng minh kết quả đúng mỗi khi dừng chưa đủ để chứng minh chương trình thực sự giải quyết xong bài toán.

Ví dụ, một hàm cần trả 0 nhưng bị kẹt trong vòng lặp vô hạn. Hàm không trả giá trị khác 0; tuy nhiên, người gọi vẫn không nhận được câu trả lời. Đó chính là khoảng cách giữa hai mức tính đúng.

## 2. Đặc tả bằng tiền điều kiện và hậu điều kiện

Cho chương trình hoặc thuật toán S, **tiền điều kiện P** và **hậu điều kiện Q**, ta viết bộ ba Hoare:

~~~text
{P} S {Q}
~~~

- **P:** điều kiện phải đúng trước khi chạy S. Ví dụ, mảng khác null và đã được sắp xếp; hoặc hai số đầu vào đều dương.
- **S:** đoạn chương trình cần phân tích, có thể chứa gán, rẽ nhánh, vòng lặp, lời gọi hàm hoặc đệ quy.
- **Q:** điều kiện cần đúng ở trạng thái cuối sau khi S **kết thúc bình thường**; ví dụ kết quả bằng ước chung lớn nhất hoặc mảng đã được sắp tăng dần.

Trong cách hiểu **đúng bộ phận**, bộ ba trên có nghĩa:

> Với mọi trạng thái đầu thỏa P, **nếu** S kết thúc bình thường thì trạng thái cuối phải thỏa Q.

Trong cách hiểu **đúng toàn phần**, yêu cầu mạnh hơn:

> Với mọi trạng thái đầu thỏa P, S **phải kết thúc bình thường** và trạng thái cuối phải thỏa Q.

Các định nghĩa ở đây xét sự kết thúc bình thường; ngoại lệ, lỗi runtime và hủy tác vụ cần được mô hình hóa riêng nếu chúng nằm trong hợp đồng. Với thuật toán có nhiều khả năng thực thi (không đơn định), chứng minh tính đúng toàn phần thường đòi hỏi **mọi cách thực thi được phép** đều kết thúc và thỏa Q, trừ khi đặc tả nêu rõ giả định như tính công bằng của bộ lập lịch.

**Quan hệ cốt lõi:**

- Đúng toàn phần ⇒ đúng bộ phận.
- Đúng bộ phận ⇏ đúng toàn phần.
- Đúng bộ phận + chứng minh kết thúc (trên toàn bộ miền P) ⇒ đúng toàn phần.

Không được thay chữ “nếu dừng” trong đúng bộ phận bằng “sẽ dừng”; hai phát biểu có nội dung logic khác nhau.

## 3. So sánh hai mức tính đúng

| Tiêu chí | Đúng bộ phận | Đúng toàn phần |
| --- | --- | --- |
| Phải có tiền điều kiện P và hậu điều kiện Q rõ ràng | Có | Có |
| Bảo đảm Q nếu chương trình kết thúc bình thường | Có | Có |
| Bảo đảm chương trình kết thúc với mọi đầu vào thỏa P | Không | Có |
| Có thể đúng khi chương trình lặp vô hạn ở một số đầu vào thỏa P | Có | Không |
| Cần chứng minh tính đúng của trạng thái cuối | Có | Có |
| Cần thêm chứng minh dừng | Không bắt buộc | Bắt buộc |
| Hữu ích trong | Lập luận về kết quả, bất biến, các bước đặc tả | Chứng minh thuật toán thực sự giải xong bài toán |

Ba tình huống cần phân biệt:

1. **Dừng và trả kết quả sai:** không đạt đúng bộ phận, vì có phản ví dụ đầu vào thỏa P nhưng kết quả vi phạm Q; do đó cũng không đúng toàn phần.
2. **Mọi lần kết thúc đều đúng, nhưng có đầu vào hợp lệ khiến thuật toán chạy mãi:** có thể đúng bộ phận nhưng không đúng toàn phần.
3. **Mọi đầu vào hợp lệ đều dừng và trả đúng:** đạt cả hai; đây là đúng toàn phần.

Chữ “mọi” là thiết yếu: chạy thử thành công trên một số ví dụ không chứng minh tính đúng toàn phần cho toàn bộ miền đầu vào.

## 4. Ví dụ phản trực giác: đúng bộ phận dù không dừng

Xét một hàm Java minh họa dưới đây. Đây **chỉ là trích đoạn minh họa**, không phải chương trình đầy đủ để chạy; **đừng gọi hàm với n > 0** vì nó sẽ chạy mãi:

~~~java
static int maybeStops(int n) {
    while (n > 0) {
        // n không thay đổi: n > 0 sẽ luôn đúng nếu ban đầu n > 0
    }
    return n;
}
~~~

Đặt P là “n là một số nguyên int bất kỳ” và Q là “giá trị trả về ≤ 0”.

- Nếu n ≤ 0, vòng lặp không chạy, hàm trả n và Q đúng.
- Nếu n > 0, n không bao giờ thay đổi, nên vòng lặp không kết thúc. Không có trạng thái trả về để vi phạm Q.
- Vì **mọi lần kết thúc bình thường** đều trả số không dương, hàm thỏa **đúng bộ phận** theo P, Q này.
- Vì có những đầu vào thỏa P (như n = 1) khiến hàm chạy vô hạn, hàm **không đúng toàn phần**.

Một trường hợp còn cực đoan hơn là vòng lặp vô hạn không có lối ra: theo định nghĩa đúng bộ phận, bộ ba có thể đúng với bất kỳ Q nào, kể cả Q sai, vì **không có lần kết thúc bình thường nào để làm phản ví dụ**. Hiện tượng này gọi là tính đúng “rỗng” (vacuous truth). Nó cho thấy chỉ dùng đúng bộ phận có thể không đáp ứng mục tiêu của một thuật toán cần tạo ra đáp án.

Lưu ý: đúng bộ phận **không có nghĩa là “chương trình đúng trên một phần dữ liệu”**. Từ “bộ phận” nói về phần nghĩa vụ chứng minh: đúng của kết quả **nếu** dừng, chứ không phải tỷ lệ test pass.

## 5. Chứng minh đúng bộ phận bằng bất biến vòng lặp

Với vòng lặp dạng “while B do C”, một phương pháp cơ bản là tìm **bất biến vòng lặp I (loop invariant)** — một mệnh đề đúng ở đầu mọi lần kiểm tra điều kiện B.

Để lập luận đúng bộ phận, thường chứng minh ba nghĩa vụ:

1. **Khởi tạo:** từ P và phần lệnh trước vòng lặp, suy ra I đúng trước lần kiểm tra B đầu tiên.
2. **Bảo toàn:** nếu I và B đúng trước thân vòng lặp, thì chạy thân C xong vẫn có I.
3. **Thoát:** nếu vòng lặp kết thúc, ta có I và phủ định B; từ đó cùng phần lệnh sau vòng lặp suy ra Q.

Có thể ghi phác thảo:

~~~text
P  =>  I
{I ∧ B} C {I}
I ∧ ¬B  =>  Q

=> Chứng minh hậu điều kiện Q mỗi khi vòng lặp kết thúc.
~~~

Ba nghĩa vụ này **chưa tự chứng minh vòng lặp sẽ kết thúc**. Bất biến cho biết một tính chất vẫn đúng trong lúc chạy; bất biến có thể được duy trì mãi mãi trong một vòng lặp vô hạn.

Ví dụ, bất biến “x ≥ 0” vẫn đúng sau câu lệnh “x = x” khi x ban đầu không âm; song không có lý do nào để tin vòng lặp “while (x > 0)” chứa câu lệnh đó sẽ dừng.

## 6. Chứng minh dừng để đạt đúng toàn phần

Bên cạnh bất biến, ta tìm một **hàm biến thiên giảm (loop variant, ranking function)** V trên trạng thái chương trình. Trường hợp phổ biến nhất là V nhận giá trị trong tập số nguyên không âm.

Với mỗi lần vòng lặp thực hiện thân C khi điều kiện B đúng, ta chứng minh:

1. **Bị chặn dưới:** V ≥ 0 tại các trạng thái liên quan.
2. **Giảm nghiêm ngặt:** V sau mỗi lần chạy thân C nhỏ hơn V trước lần đó.
3. **Mỗi lần lặp kết thúc hữu hạn và không phát sinh đường chạy bất thường ngoài đặc tả:** để việc giảm V thực sự gắn với quá trình thực thi.

Không có chuỗi giảm nghiêm ngặt vô hạn của các số nguyên không âm. Vì vậy, với các giả định thực thi thích hợp, vòng lặp không thể chạy mãi: cuối cùng điều kiện lặp phải sai.

Ví dụ với đoạn:

~~~java
int x = n;             // Giả sử n >= 0
while (x > 0) {
    x = x - 1;
}
~~~

- **Bất biến:** 0 ≤ x ≤ n, được thiết lập lúc khởi tạo và được bảo toàn.
- **Biến thiên giảm:** V = x. Khi x > 0 thì x giảm đúng 1 và vẫn không âm.
- **Kết thúc:** sau n lần lặp (với n ≥ 0), x = 0.
- **Hậu điều kiện:** x = 0 sau khi thoát vòng lặp.

Đây là một ví dụ đúng toàn phần cho tiền điều kiện n ≥ 0 và hậu điều kiện x = 0. Đoạn mã là trích đoạn nằm trong một phương thức, không phải tệp Java độc lập.

Với thuật toán đệ quy, ý tưởng tương tự: tìm đại lượng có thứ tự tốt giảm sau **mỗi** lời gọi đệ quy được thực hiện. Ví dụ, n giảm đến 0 trong một hàm đệ quy có điều kiện dừng đúng. Nếu dùng số thực không âm làm biến thiên mà chỉ chứng minh giảm nghiêm ngặt, điều đó **chưa đủ** vì có chuỗi vô hạn 1, 1/2, 1/4, ...; phải chứng minh giảm trên một tập có thứ tự tốt hoặc dùng lập luận dừng mạnh hơn.

## 7. Ví dụ hoàn chỉnh Java 17+: thuật toán Euclid tìm UCLN

Xét bài toán tính ước chung lớn nhất (UCLN) của hai số nguyên dương a và b bằng thuật toán Euclid.

**Hợp đồng của gcd(a, b):**

- **P:** a > 0 và b > 0.
- **Q:** hàm trả về số nguyên dương g = gcd(a, b), tức UCLN toán học của hai số đầu vào.
- **Đầu vào vi phạm P:** ném IllegalArgumentException với thông báo đã quy định; không nằm trong bảo đảm kết thúc bình thường của P, Q.
- **Yêu cầu đúng toàn phần:** mọi cặp a, b thỏa P đều khiến hàm kết thúc bình thường và trả đúng g.

Tạo tệp **GcdCorrectnessDemo.java** với nội dung đầy đủ sau:

~~~java
public class GcdCorrectnessDemo {
    public static int gcd(int a, int b) {
        if (a <= 0 || b <= 0) {
            throw new IllegalArgumentException("a and b must be positive");
        }

        int x = a;
        int y = b;

        while (y != 0) {
            int remainder = x % y;
            x = y;
            y = remainder;
        }

        return x;
    }

    public static void main(String[] args) {
        System.out.println("gcd(48, 18) = " + gcd(48, 18));
        System.out.println("gcd(17, 13) = " + gcd(17, 13));
        System.out.println("gcd(12, 12) = " + gcd(12, 12));

        try {
            gcd(0, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên từ thư mục chứa tệp:

~~~bash
javac GcdCorrectnessDemo.java
java GcdCorrectnessDemo
~~~

Đầu ra chính xác:

~~~text
gcd(48, 18) = 6
gcd(17, 13) = 1
gcd(12, 12) = 12
invalid: a and b must be positive
~~~

Ta sẽ chứng minh hai phần độc lập: **giữ đúng kết quả nếu dừng**, và **chắc chắn dừng**.

### 7.1. Phần A — Chứng minh đúng bộ phận

Chọn bất biến I tại đầu mỗi vòng lặp:

- x > 0.
- y ≥ 0.
- gcd(x, y) = gcd(a, b), trong đó a, b là các tham số đầu vào ban đầu.

**Khởi tạo:** do a > 0 và b > 0, sau hai phép gán x = a, y = b, ba điều của I đều đúng.

**Bảo toàn:** giả sử I đúng và điều kiện lặp y != 0 đúng. Vì y ≥ 0 nên y > 0. Java tính “remainder = x % y”; với x > 0 và y > 0, ta có 0 ≤ remainder < y. Sau các lệnh gán x = y, y = remainder, ta vẫn có x > 0 và y ≥ 0. Đồng nhất thức của Euclid:

~~~text
gcd(x, y) = gcd(y, x mod y), với x > 0 và y > 0
~~~

chứng minh UCLN không đổi sau mỗi bước. Do đó I được bảo toàn.

**Khi thoát:** điều kiện y != 0 sai, tức y = 0. Từ bất biến:

~~~text
gcd(x, 0) = x = gcd(a, b)   (vì x > 0)
~~~

Vì hàm trả x, hậu điều kiện Q đúng **nếu vòng lặp kết thúc**. Đây là chứng minh đúng bộ phận.

### 7.2. Phần B — Chứng minh kết thúc

Chọn **V = y** làm biến thiên giảm:

- Từ bất biến, y ≥ 0.
- Mỗi lần vào vòng lặp đều có y > 0.
- Sau phép lấy phần dư, y mới bằng x cũ mod y cũ, nên 0 ≤ y mới < y cũ.
- Tất cả phép tính trên số nguyên dương int hợp lệ: phép lấy dư với số chia dương không gặp chia cho 0 trong thân vòng lặp, và các phép gán không gây tràn số.

Vì V là số nguyên không âm và giảm nghiêm ngặt sau mỗi lần lặp, vòng lặp phải dừng. Khi đã dừng, chứng minh ở phần A bảo đảm kết quả là UCLN. **Vậy thuật toán Euclid đúng toàn phần trên miền a > 0, b > 0.**

Vết chạy với đầu vào (48, 18):

| Thời điểm | x | y (V) | Điều kiện y != 0 |
| --- | ---: | ---: | --- |
| Ban đầu | 48 | 18 | Đúng |
| Sau vòng 1 | 18 | 12 | Đúng |
| Sau vòng 2 | 12 | 6 | Đúng |
| Sau vòng 3 | 6 | 0 | Sai; trả 6 |

Bảng chạy chỉ giúp **minh họa** lập luận. Bằng chứng tổng quát nằm ở bất biến và biến thiên giảm, không nằm ở một ví dụ có ba vòng lặp.

## 8. Quan hệ giữa chứng minh dừng và chi phí tính toán

Trong chủ đề **tính đúng và chi phí**, cần tách thêm hai vấn đề:

- **Chứng minh kết thúc:** trả lời “có chắc dừng không?”.
- **Phân tích độ phức tạp:** trả lời “cần bao nhiêu bước, thời gian hoặc bộ nhớ khi kích thước đầu vào tăng?”.

Biến thiên nguyên không âm giảm ít nhất 1 mỗi vòng có thể cho một cận trên số vòng lặp bằng giá trị ban đầu của nó. Nhưng để có cận tốt hơn, cần phân tích mức giảm thực tế.

Trong thuật toán Euclid, V = y đủ chứng minh dừng. Để có cận thời gian chặt hơn, dùng tính chất các số dư giảm nhanh: sau bước chuẩn hóa ban đầu nếu cần, trong nhiều nhất hai phép chia lấy dư, số dư đang xét giảm xuống dưới một nửa giá trị cũ. Vì vậy, số vòng lặp là **O(log(min(a, b) + 1))**; mỗi vòng có số lượng cố định phép toán số nguyên int, và chỉ cần O(1) bộ nhớ phụ.

Không nên suy diễn rằng “đã có bất biến thì tự động dừng”, cũng không nên kết luận một cận O(log n) chỉ từ việc biến thiên giảm. **Chứng minh đúng, chứng minh dừng và chứng minh độ phức tạp** là ba nhiệm vụ liên quan nhưng khác nhau.

Lưu ý khi chuyển sang số nguyên kích thước tùy ý: chi phí một phép chia lấy dư phụ thuộc số bit của toán hạng; khi ấy không thể mặc nhiên coi từng phép chia là O(1) theo số bit như với mô hình số nguyên máy cố định.

## 9. Phản ví dụ: dừng nhưng trả sai

Chứng minh dừng **không thể thay** chứng minh hậu điều kiện. Xét đoạn minh họa:

~~~java
int x = n;            // Giả sử n >= 0
while (x > 0) {
    x = x - 2;
}
// Mong muốn hậu điều kiện: x == 0
~~~

- Nếu n = 4, các giá trị x đi qua 4, 2, 0: vòng lặp dừng và x = 0.
- Nếu n = 3, các giá trị x đi qua 3, 1, -1: vòng lặp vẫn dừng nhưng x != 0.
- Với P là n ≥ 0 và Q là x = 0, chương trình **không đúng bộ phận** vì có phản ví dụ n = 3; do đó cũng **không đúng toàn phần**.
- Nếu sửa tiền điều kiện thành “n là số nguyên chẵn không âm”, lập luận có thể chứng minh đúng toàn phần: x luôn chẵn không âm khi còn vào vòng lặp, giảm 2 đến 0. Đây là một **đặc tả khác**, không phải cách chứng minh chương trình cũ đúng cho mọi số không âm.

Ví dụ này cho thấy ba khía cạnh phải khớp nhau: **miền đầu vào P**, **hậu điều kiện Q**, và **hành vi thực tế của thuật toán S**. Không được “chữa” chứng minh bằng cách tự ý thay đổi đặc tả của đề bài.

## 10. Đúng toàn phần của hàm đệ quy và chương trình thực tế

Với đệ quy, một chứng minh đúng bộ phận có thể dựa vào giả thiết quy nạp rằng lời gọi con trả kết quả đúng nếu nó kết thúc. Để chứng minh đúng toàn phần, cần bổ sung rằng mọi nhánh đệ quy đều tiến gần trường hợp cơ sở theo một thước đo có thứ tự tốt, chẳng hạn n giảm trong tập số nguyên không âm.

Trong chương trình thực tế, lưu ý các ranh giới sau:

- **Tiền điều kiện quan trọng:** với gcd ở trên, số âm và số 0 được từ chối bằng ngoại lệ. Chứng minh đúng toàn phần đã nêu chỉ áp dụng cho a > 0, b > 0; nếu muốn đặc tả hỗ trợ số âm hoặc 0, phải thiết kế và chứng minh lại miền đầu vào.
- **Ngoại lệ hoặc lỗi:** trong một hợp đồng có xét ngoại lệ, cần mô tả cả hậu điều kiện bình thường lẫn hậu điều kiện ngoại lệ. Không được tính việc ném ngoại lệ bất ngờ là “đã dừng thành công”.
- **Môi trường và thao tác chờ:** đọc từ mạng, chờ khóa hoặc xử lý đồng thời có thể phụ thuộc tác nhân ngoài. Chứng minh dừng có thể phải giả định tài nguyên, lịch chạy hoặc thao tác bên ngoài hoàn thành.
- **Giới hạn thực thi:** một thuật toán có thể dừng về mặt toán học nhưng vượt thời gian, bộ nhớ hoặc stack của môi trường cụ thể; cần phân biệt đặc tả lý thuyết với giới hạn vận hành.
- **Tính không đơn định:** nếu thuật toán có nhiều đường chạy được phép, một đường chạy đúng và dừng không đủ để chứng minh tất cả đường chạy đều dừng và đúng.

Những lưu ý này giúp phát biểu phạm vi chứng minh trung thực: thuật toán nào, đầu vào nào, mô hình thực thi nào và hợp đồng bình thường/ngoại lệ nào đang được xét.

## 11. Quy trình thực hành khi đánh giá một thuật toán

**Bước 1 — Viết rõ P, Q và kiểu kết thúc cần bảo đảm.** Ví dụ, đầu vào là hai số nguyên dương, đầu ra là UCLN; hoặc mảng tăng dần và chỉ số trả về khớp khóa.

**Bước 2 — Chứng minh đúng bộ phận.** Với vòng lặp, tìm bất biến I, rồi kiểm tra khởi tạo, bảo toàn và suy ra Q khi thoát. Với đệ quy, xây dựng lập luận quy nạp rõ ràng.

**Bước 3 — Chứng minh kết thúc.** Tìm biến thiên/ranking function, chỉ ra nó nằm trong một tập có thứ tự tốt và giảm nghiêm ngặt sau mỗi bước phù hợp. Kiểm tra mọi nhánh có thể thực thi.

**Bước 4 — Kết luận đúng toàn phần nếu cả hai phần đều thành công.** Chỉ một trong hai phần thành công thì không thể kết luận đúng toàn phần.

**Bước 5 — Phân tích chi phí riêng.** Số vòng lặp, độ phức tạp, bộ nhớ phụ và giới hạn tài nguyên. Dùng kết quả chứng minh dừng để hỗ trợ phân tích nhưng đừng nhầm hai nhiệm vụ.

**Bước 6 — Kiểm thử các lớp đầu vào.** Ví dụ: giá trị nhỏ nhất, giá trị biên, trường hợp làm điều kiện lặp sai ngay, trường hợp chạy nhiều vòng, đầu vào không hợp lệ. Kiểm thử giúp tìm phản ví dụ nhưng không thay chứng minh với mọi đầu vào P.

Bảng tự kiểm tra nhanh:

| Phát biểu | Đúng hay sai? | Vì sao? |
| --- | --- | --- |
| “Hàm luôn trả đúng nếu trả về; vậy nó đúng toàn phần.” | Sai | Chưa chứng minh mọi đầu vào hợp lệ đều kết thúc |
| “Hàm dừng với mọi đầu vào; vậy nó đúng toàn phần.” | Sai | Có thể dừng và trả sai Q |
| “Chứng minh I được bảo toàn và I ∧ ¬B suy ra Q.” | Chưa đủ | Mới cho đúng bộ phận; cần chứng minh dừng |
| “Có biến thiên nguyên không âm và giảm nghiêm ngặt mỗi vòng.” | Đủ để suy ra vòng lặp dừng trong điều kiện thực thi phù hợp | Chưa tự chứng minh Q |
| “Đúng bộ phận và đã chứng minh dừng cho mọi đầu vào thỏa P.” | Đúng | Đủ kết luận đúng toàn phần theo hợp đồng đã nêu |

## 12. Bài tập tự luyện có định hướng

**Bài 1.** Cho thuật toán tìm tuyến tính một phần tử trong mảng hữu hạn. Hãy viết P và Q; chứng minh bằng bất biến rằng các phần tử đã duyệt đều khác khóa khi chưa tìm thấy; dùng số phần tử chưa duyệt làm biến thiên giảm. Tách rõ trường hợp “không tìm thấy” hợp lệ khỏi đầu vào null không hợp lệ.

**Bài 2.** Cho đoạn lặp “while (n > 0) { n = n / 2; }” với n là số nguyên int. Chứng minh đúng toàn phần dưới P: n ≥ 0, Q: n = 0. Gợi ý: bất biến n ≥ 0; khi n > 0, phép chia nguyên cho 2 cho số nhỏ hơn n và không âm, nên dùng n làm biến thiên.

**Bài 3.** Một thuật toán có hậu điều kiện Q được kiểm tra đúng trên 10.000 dữ liệu nhưng có một đường chạy không dừng khi điều kiện P vẫn đúng. Có thể gọi nó đúng toàn phần không? **Không**: một phản ví dụ không dừng đã bác bỏ yêu cầu dừng phổ quát. Muốn nói nó đúng bộ phận còn phải bảo đảm *mọi* lần kết thúc bình thường thỏa Q, không chỉ 10.000 mẫu.

**Bài 4.** Xét vòng lặp giảm biến x bằng 2 ở mục 9. Hãy chỉ ra P đủ mạnh để Q là x = 0, hoặc giữ P là x ≥ 0 rồi sửa Q thành “x bằng 0 hoặc -1”. Cần chứng minh lại bất biến và điều kiện thoát cho hợp đồng đã chọn.

**Ghi nhớ:** **đúng bộ phận = nếu kết thúc thì đúng kết quả**; **đúng toàn phần = chắc chắn kết thúc và đúng kết quả**. Với vòng lặp, **bất biến** là công cụ trung tâm để chứng minh hậu điều kiện, còn **biến thiên giảm** là công cụ trung tâm để chứng minh dừng. Hai chứng minh kết hợp mới bảo đảm thuật toán giải xong bài toán theo đặc tả.
