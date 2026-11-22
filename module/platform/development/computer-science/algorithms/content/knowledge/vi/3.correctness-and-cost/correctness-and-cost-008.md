# Thời gian, bộ nhớ phụ và chi phí lưu kết quả

Khi đánh giá thuật toán, câu hỏi “thuật toán tốn bao nhiêu tài nguyên?” cần được tách thành ba phần: **thời gian thực hiện**, **bộ nhớ phụ để tính toán**, và **chi phí tạo, lưu hoặc truyền kết quả**. Ba phần này liên quan nhưng không thay thế cho nhau. Một thuật toán có thể dùng rất ít bộ nhớ tạm nhưng tạo ra kết quả lớn; ngược lại, hai thuật toán có thời gian tính toán tương tự vẫn có nhu cầu RAM khác nhau vì một thuật toán giữ toàn bộ kết quả trong bộ nhớ.

Chủ đề này thuộc phần **Tính đúng và chi phí**: trước tiên, thuật toán phải tạo đúng kết quả mà đặc tả yêu cầu; tiếp theo mới so sánh cách sử dụng thời gian, bộ nhớ và đầu ra.

## 1. Xác định đầu vào, đầu ra và mô hình đo chi phí

Ký hiệu thường dùng:

- \(n\): kích thước đầu vào, chẳng hạn số phần tử mảng, số ký tự, số đỉnh. Với đồ thị có thể cần hai tham số \(V\) (đỉnh) và \(E\) (cạnh).
- \(k\): **số phần tử của kết quả**. Có những bài toán \(k\) thay đổi theo đầu vào và lớn hơn nhiều so với \(n\).
- \(B_{\text{out}}\): kích thước biểu diễn đầu ra, tính bằng byte hoặc ký tự. Hai kết quả đều có \(k\) phần tử nhưng có thể khác \(B_{\text{out}}\) vì độ dài mỗi phần tử khác nhau.
- \(T(n,k)\): số bước công việc của thuật toán theo mô hình tính toán đã nêu; khi ghi ra tệp hoặc mạng, có thể phân tích thêm chi phí I/O theo \(B_{\text{out}}\).
- \(S_{\text{aux}}(n,k)\): **bộ nhớ phụ** (auxiliary space), tức bộ nhớ làm việc ngoài phần lưu đầu vào và phần lưu kết quả, theo quy ước đã công bố.
- \(S_{\text{result}}(n,k)\): dung lượng cần để giữ kết quả nếu kết quả được **hiện thực hóa đầy đủ** (materialize) trong RAM hoặc trên thiết bị lưu trữ.

Với cùng một bài toán, nên mô tả cả **thời gian để sinh kết quả** và **cách trả kết quả**. Nếu API bắt buộc trả về một danh sách gồm \(k\) phần tử, dung lượng danh sách là chi phí có thật dù một tài liệu về độ phức tạp bộ nhớ phụ có thể không tính nó vào \(S_{\text{aux}}\).

Cần công bố **quy ước đếm** trước khi so sánh:

| Đại lượng | Tính những gì? | Dễ nhầm với |
|---|---|---|
| Thời gian \(T\) | Đọc dữ liệu, thao tác tính toán, tạo phần tử kết quả; có thể tính thêm ghi I/O theo mục đích phân tích | Chỉ đếm vòng lặp xử lý đầu vào rồi bỏ qua bước xuất dữ liệu |
| Bộ nhớ phụ \(S_{\text{aux}}\) | Biến tạm, cấu trúc trung gian, ngăn xếp đệ quy; không tính dữ liệu đầu vào và đối tượng kết quả theo quy ước này | Tổng RAM của tiến trình |
| Bộ nhớ kết quả \(S_{\text{result}}\) | Mảng, danh sách, cây, chuỗi... thực sự được giữ để trả kết quả | Bộ nhớ tạm của thuật toán |
| Tổng bộ nhớ đỉnh | Những đối tượng còn sống đồng thời, gồm đầu vào, tạm và kết quả khi cùng tồn tại | Tổng byte đã từng cấp phát trong suốt quá trình chạy |
| Chi phí ghi/lưu đầu ra | Số byte được mã hóa, ghi ra màn hình, tệp, mạng hoặc cơ sở dữ liệu | Chỉ số lượng phần tử \(k\) |

Ví dụ, một lời giải có thể được ghi là **thời gian \(O(n)\), bộ nhớ phụ \(O(1)\), bộ nhớ kết quả \(O(n)\)**. Điều này hoàn toàn nhất quán nếu thuật toán tạo một mảng kết quả dài \(n\), chỉ sử dụng vài biến tạm. Nếu mảng đó phải nằm trong RAM đồng thời với dữ liệu đầu vào, tổng bộ nhớ đỉnh không phải \(O(1)\).

**Độ phức tạp tiệm cận không phải dung lượng tuyệt đối.** Mảng gồm một triệu phần tử kiểu int trong Java có khoảng 4 MB dữ liệu số nguyên (chưa kể header, căn chỉnh và các đối tượng khác). Danh sách một triệu đối tượng có chi phí khác xa vì còn có tham chiếu và overhead của đối tượng. Dùng \(O(n)\) để nêu tốc độ tăng, dùng phép đo hoặc ước lượng byte để lập ngân sách thực tế.

## 2. Thời gian: tính cả việc tạo và đưa kết quả ra ngoài

Trong mô hình RAM cơ bản, một phép so sánh, truy cập mảng hoặc thao tác trên một từ máy có thể được xem là \(O(1)\). Khi viết \(T(n)=O(n)\), ta đang chặn số thao tác theo \(n\), không khẳng định chương trình luôn chạy trong một số mili giây cụ thể.

Các ký hiệu cần dùng đúng:

- \(O(g(n))\) là **cận trên tiệm cận**.
- \(\Omega(g(n))\) là **cận dưới tiệm cận**.
- \(\Theta(g(n))\) là **cận chặt cả trên lẫn dưới**.

Ví dụ, duyệt hết mảng \(n\) phần tử một lần có \(\Theta(n)\) bước trong mô hình phần tử kích thước cố định. Nếu một vòng lặp tạo ra \(k\) phần tử và mỗi phần tử mất ít nhất một bước để xuất, việc xuất **từng phần tử một cách tường minh** cần ít nhất \(\Omega(k)\) bước. Khi giá trị đầu ra phải mã hóa thành \(B_{\text{out}}\) byte, thiết bị với băng thông hữu hạn còn phải truyền hoặc lưu lượng byte tương ứng. Mô hình I/O theo block có thể tính số block thay vì số byte; phải nói rõ nếu dùng mô hình đó.

Vì thế, khi kết quả lớn, một biểu thức chi phí có ích là \(T(n,k)\), hoặc \(T_{\text{prepare}}(n)+T_{\text{generate}}(n,k)+T_{\text{emit}}(B_{\text{out}})\). Đây là cách phân tích các phần việc, không phải công thức cố định cho mọi thuật toán: một triển khai có thể xen kẽ tính toán và ghi I/O.

**Lỗi thường gặp:** phân tích bước tìm kiếm là \(O(n)\), sau đó gọi toàn bộ chương trình là \(O(n)\) dù chương trình còn sao chép hay in \(n^2\) kết quả. Việc trả kết quả là một phần của yêu cầu đầu ra nếu đặc tả đòi hỏi trả đủ các phần tử đó.

## 3. Bộ nhớ phụ và bộ nhớ lưu kết quả

**Bộ nhớ phụ** trả lời: “Trong lúc giải, ngoài đầu vào và kết quả, còn phải giữ gì?” Ví dụ:

- Tìm phần tử lớn nhất trong mảng bằng một biến best và một chỉ số: \(O(1)\) bộ nhớ phụ.
- Duyệt đồ thị bằng DFS đệ quy: ngăn xếp lời gọi có thể sâu đến \(O(V)\), chưa tính cấu trúc đánh dấu đỉnh.
- Sinh mọi tập con bằng quay lui: đường đi hiện tại và ngăn xếp có thể tốn \(O(n)\) bộ nhớ phụ; nếu lưu mọi tập con vào danh sách thì phần kết quả còn lớn hơn rất nhiều.

**Bộ nhớ kết quả** trả lời: “Để trả đúng kiểu kết quả mà giao diện yêu cầu, phải giữ bao nhiêu dữ liệu?” Nếu trả một mảng gồm \(n\) tổng tiền tố, mảng kết quả tốn \(\Theta(n)\) phần tử dù vòng lặp tính chỉ cần \(O(1)\) biến phụ. Nếu trả một số đếm duy nhất thì kết quả có thể chiếm \(O(1)\) từ máy; nhưng “trả số lượng” là yêu cầu khác với “liệt kê tất cả phần tử”.

Cần phân biệt ba cách nói về bộ nhớ:

1. **Peak live memory:** các dữ liệu đang cùng tồn tại ở thời điểm tốn nhiều RAM nhất. Thường quyết định nguy cơ hết bộ nhớ.
2. **Total allocations:** tổng cấp phát trong suốt quá trình, kể cả những đối tượng ngắn hạn đã được giải phóng/thu gom. Chỉ số này ảnh hưởng đến GC và hiệu năng nhưng không đồng nhất với peak.
3. **Persistent storage:** byte còn lưu trên tệp/đĩa/cơ sở dữ liệu sau khi phép tính kết thúc. Ghi trực tiếp ra tệp có thể giảm RAM nhưng không làm mất chi phí lưu trữ.

Nếu danh sách kết quả dùng mảng động như ArrayList, dung lượng cấp phát thường có thể lớn hơn số phần tử hiện tại, và lúc mở rộng mảng có thể có thời điểm mảng cũ lẫn mảng mới cùng tồn tại. Khi phân tích theo bậc tăng trưởng, lưu \(k\) phần tử vẫn cần \(O(k)\) dung lượng; các hệ số và peak thực tế phải đo nếu bộ nhớ là ràng buộc nghiêm ngặt.

## 4. Ví dụ cốt lõi: liệt kê mọi cặp chỉ số khác nhau

Cho \(n\) chỉ số \(1,2,\ldots,n\). Yêu cầu **liệt kê tất cả cặp \((i,j)\) với \(i<j\)**. Số cặp là:

\[
k=\sum_{i=1}^{n}(n-i)=\frac{n(n-1)}{2}=\Theta(n^2).
\]

Khi \(n=4\), sáu cặp là \((1,2),(1,3),(1,4),(2,3),(2,4),(3,4)\). Hai chiến lược tạo *cùng tập cặp* nhưng phân bổ tài nguyên khác nhau:

| Chiến lược | Thao tác chính | Bộ nhớ phụ theo mô hình từ máy | Nơi chứa kết quả |
|---|---|---|---|
| **Lưu toàn bộ** | Sinh từng cặp và thêm vào danh sách, sau đó trả danh sách | Vài chỉ số vòng lặp \(O(1)\), khi tách phần danh sách ra khỏi số liệu bộ nhớ phụ | Danh sách \(\Theta(k)=\Theta(n^2)\) phần tử; tổng RAM đỉnh tăng cùng \(k\) |
| **Phát từng cặp** | Sinh một cặp và chuyển ngay cho bộ nhận (consumer, bộ ghi, luồng xử lý) | \(O(1)\) từ máy cho chỉ số, ngoài bộ đệm hữu hạn của nơi nhận | Không giữ cả danh sách trong RAM; dữ liệu đã phát có thể được lưu ở nơi nhận |

Cả hai đều phải **sinh \(\Theta(n^2)\) cặp**; streaming không biến số lượng cặp thành \(O(n)\). Điểm lợi chính là không giữ mọi cặp cùng lúc. Nếu bộ nhận tự gom tất cả cặp lại, chi phí bộ nhớ \(\Theta(n^2)\) sẽ xuất hiện ở bộ nhận: streaming chỉ có lợi khi toàn bộ luồng xử lý không hiện thực hóa kết quả.

Lưu ý sự khác nhau giữa **số cặp** và **số ký tự xuất**. Nếu in \(i\) và \(j\) dưới dạng số thập phân, một dòng có \(O(\log n)\) chữ số trong phân tích lý thuyết với \(n\) tăng không giới hạn. Vì vậy kích thước văn bản của toàn bộ kết quả có thể là \(\Theta(n^2\log n)\) ký tự, dù ta vẫn thường tính mỗi cặp gồm hai số nguyên là \(O(1)\) *từ máy* trong mô hình RAM. Java dùng int có miền hữu hạn nên với chương trình cụ thể cần nêu giới hạn kiểu dữ liệu và cách in.

## 5. Java 17+: lưu danh sách so với in từng kết quả

Chương trình sau minh họa hai cách hiện thực hóa đầu ra. Dùng **record Pair** để lưu một cặp; một phương thức trả List<Pair>, phương thức còn lại in từng cặp mà không xây dựng List<Pair>. Ví dụ cố ý dùng \(n=4\) để có thể kiểm tra toàn bộ đầu ra bằng mắt.

Tạo tệp **PairCostDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PairCostDemo {
    record Pair(int left, int right) {}

    static List<Pair> materializePairs(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be non-negative");
        }

        List<Pair> result = new ArrayList<>();
        for (int i = 1; i <= n; i++) {
            for (int j = i + 1; j <= n; j++) {
                result.add(new Pair(i, j));
            }
        }
        return result;
    }

    static void printPairs(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be non-negative");
        }

        for (int i = 1; i <= n; i++) {
            for (int j = i + 1; j <= n; j++) {
                System.out.println(i + "-" + j);
            }
        }
    }

    public static void main(String[] args) {
        int n = 4;
        List<Pair> pairs = materializePairs(n);
        System.out.println("Stored pairs: " + pairs.size());

        System.out.println("Streaming pairs:");
        printPairs(n);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac PairCostDemo.java
java PairCostDemo
~~~

Stdout chính xác:

~~~text
Stored pairs: 6
Streaming pairs:
1-2
1-3
1-4
2-3
2-4
3-4
~~~

**Phân tích từng phương thức:**

- materializePairs tạo \(\frac{n(n-1)}{2}\) bản ghi, nên thời gian sinh cặp là \(\Theta(n^2)\) theo phép toán trên cặp có kích thước từ máy. Danh sách trả về tốn \(\Theta(n^2)\) phần tử; các biến vòng lặp riêng lẻ là \(O(1)\) từ máy. Nếu phân tích *tổng RAM đỉnh*, phải tính cả các mảng nội bộ và đối tượng Pair.
- printPairs cũng duyệt \(\Theta(n^2)\) cặp. Nó không lưu danh sách, nhưng phải tạo chuỗi cho từng dòng và gọi System.out.println. Bộ nhớ làm việc cho một dòng phụ thuộc số chữ số; I/O và định dạng số khiến thời gian thực tế khác với việc chỉ tạo bản ghi trong RAM.
- main giữ biến pairs trong lúc gọi printPairs. **Toàn chương trình minh họa vẫn có thể giữ danh sách \(O(n^2)\) trong RAM** tại thời điểm in. Muốn lợi ích bộ nhớ của streaming trong ứng dụng thực, hãy chỉ dùng nhánh phát dữ liệu hoặc bảo đảm dữ liệu đã lưu được giải phóng trước khi sinh luồng lớn.

Đây là chương trình học tập cho \(n\) nhỏ; với \(n\) lớn, số lượng kết quả tăng bậc hai có thể làm cạn RAM, thời gian hoặc giới hạn vùng giá trị của biến đếm. Trong hệ thống thực cần kiểm tra kích thước dự kiến, giới hạn yêu cầu đầu vào và đặt chính sách phân trang/streaming phù hợp.

## 6. Không thể bỏ qua chi phí kích thước đầu ra

Độ phức tạp của việc **tính mô tả ngắn** có thể nhỏ hơn nhiều so với việc **liệt kê toàn bộ kết quả**:

- **Đếm số cặp:** công thức \(n(n-1)/2\) tính bằng \(O(1)\) phép toán số nguyên từ máy, trả một giá trị; cần kiểm tra tràn số. Nếu làm số học chính xác với số nguyên không giới hạn, phép toán không còn mặc định chi phí bit \(O(1)\).
- **Liệt kê các cặp:** có \(\Theta(n^2)\) mục cần tạo. Trong mô hình xuất một mục mỗi bước, riêng việc đưa các mục ra ngoài đã có cận dưới \(\Omega(n^2)\).
- **Lưu tất cả cặp để truy cập ngẫu nhiên sau này:** cần \(\Theta(n^2)\) chỗ cho các mục nếu giữ biểu diễn tường minh; truyền ra tệp thay vì RAM chỉ chuyển nơi phát sinh chi phí lưu trữ.
- **Mô tả tất cả cặp bằng quy tắc “mọi \(i<j\)”** là một kết quả nén/ngầm định nhỏ; tuy nhiên nó **không thỏa** yêu cầu của giao diện đòi trả từng cặp tường minh.

Cận dưới “phải tốn thời gian tỷ lệ kích thước đầu ra” chỉ áp dụng khi thực sự phải xuất đầu ra tường minh theo mô hình đang xét. Một thuật toán trả **bộ mô tả ngắn**, iterator lười (lazy) hoặc công thức có thể hoàn thành bước khởi tạo rất nhanh; thời gian để **tiêu thụ hết** các kết quả vẫn phải được tính khi người dùng cần toàn bộ kết quả.

Tương tự, với bài toán liệt kê mọi tập con của \(n\) phần tử, có \(2^n\) tập con. Nếu lưu mỗi tập con bằng một danh sách phần tử, tổng số phần tử xuất hiện trong tất cả danh sách là \(n2^{n-1}\), nên dung lượng kết quả đạt \(\Theta(n2^n)\) *mục* khi \(n\ge1\). Một thuật toán quay lui có thể dùng \(O(n)\) trạng thái đường đi, nhưng việc sao chép và giữ toàn bộ danh sách kết quả vẫn tốn \(\Theta(n2^n)\) chỗ và thời gian sao chép các mục trong mô hình tương ứng.

## 7. Chi phí biểu diễn: cùng số kết quả, số byte khác nhau

Số mục kết quả \(k\) chưa đủ để biết chi phí bộ nhớ. Cần xét **cách biểu diễn mỗi mục**:

**Ví dụ mọi đoạn con (substring) của chuỗi dài \(n\):** có \(\frac{n(n+1)}{2}=\Theta(n^2)\) vị trí đoạn con. Nếu một kết quả chỉ là cặp chỉ số (start, end), bộ nhớ mô tả tất cả kết quả là \(\Theta(n^2)\) cặp chỉ số. Nhưng nếu tạo một **bản sao chuỗi ký tự độc lập** cho mỗi đoạn con, tổng số ký tự phải sao chép là

\[
\sum_{\ell=1}^{n}\ell(n-\ell+1)
=\frac{n(n+1)(n+2)}{6}
=\Theta(n^3).
\]

Như vậy, việc liệt kê chỉ số mất \(\Theta(n^2)\) phần tử, còn việc lưu toàn bộ *nội dung* các đoạn con cần \(\Theta(n^3)\) ký tự. Trên Java 17, String.substring tạo nội dung chuỗi mới thay vì đơn thuần trả về một góc nhìn dùng chung mảng ký tự của chuỗi gốc; dung lượng byte cụ thể vẫn phụ thuộc mã hóa nội bộ và ký tự. Với chuỗi nhiều ký tự Unicode, cần đo byte thực tế thay vì mặc định một ký tự luôn bằng một byte.

Ví dụ này cho thấy **thao tác sao chép**, định dạng văn bản, mã hóa UTF-8/UTF-16, đối tượng wrapper và giao thức truyền có thể biến đổi rõ rệt chi phí thời gian lẫn dung lượng, dù số mục logic của đầu ra không đổi. Thao tác tạo đoạn con dùng *view* trên dữ liệu gốc có thể giảm bản sao nhưng lại kéo dài vòng đời dữ liệu gốc, yêu cầu giữ sở hữu và tránh sửa đổi bất ngờ.

## 8. Chọn giao diện trả kết quả phù hợp

| Cách trả kết quả | Phù hợp khi | Đổi lại cần chú ý |
|---|---|---|
| **Một giá trị** (đếm, tổng, cực trị) | Bài toán chỉ yêu cầu đại lượng tổng hợp | Không thay được yêu cầu liệt kê từng phần tử |
| **Mảng/List hiện thực hóa** | Cần duyệt nhiều lần, tra cứu theo vị trí, sắp xếp toàn bộ hoặc sử dụng kết quả lâu dài | RAM tỷ lệ kích thước kết quả; có thể OOM |
| **Iterator/Iterable/Stream lười** | Có thể xử lý tuần tự, chỉ lấy tiền tố hoặc phối hợp pipeline | Chi phí tính chuyển sang lúc tiêu thụ; vấn đề vòng đời nguồn, thứ tự, lỗi giữa chừng, dùng một lần đối với Java Stream |
| **Callback/consumer** | Nguồn đẩy từng kết quả tới nơi nhận ngay khi sinh | Cần quy ước xử lý lỗi và điều tiết tốc độ nơi nhận |
| **Ghi tệp hoặc mạng từng phần** | Kết quả rất lớn, không cần giữ toàn bộ trong RAM | Dung lượng đĩa, băng thông, buffer, giao dịch và tính toàn vẹn đầu ra |

Trong Java, phương thức trả Stream không có nghĩa rằng toàn bộ thao tác là miễn phí: nhiều phép toán trung gian là lazy, nhưng các phép toán kết thúc như collect(...) có thể gom mọi kết quả vào bộ nhớ. Một pipeline gọi toList() trên \(k\) phần tử thông thường lại hiện thực hóa danh sách \(\Theta(k)\). Một pipeline gọi forEach(...) có thể xử lý từng phần tử, song nếu callback giữ chúng trong bộ nhớ thì vẫn có bộ nhớ kết quả \(\Theta(k)\). Bản thân iterator hoặc Stream cũng có trạng thái, có thể dùng bộ đệm, và đôi khi cần đóng tài nguyên.

**Phân trang (pagination)** và **xử lý theo lô (batching)** giúp giới hạn RAM phục vụ mỗi lượt, nhưng không xóa chi phí tính và lưu toàn bộ kết quả nếu cuối cùng vẫn cần tất cả. Một trang kích thước \(p\) có thể cần \(O(p)\) RAM cho trang hiện tại, còn tổng số trang và tổng byte đầu ra vẫn phụ thuộc \(k\). Nếu cần sắp xếp toàn cục, bảo đảm thứ tự hoặc tránh trùng, có thể cần cấu trúc trạng thái bổ sung; không thể mặc nhiên gọi mọi giải pháp phân trang là \(O(1)\) bộ nhớ.

## 9. Một số bài toán quen thuộc và cách ghi độ phức tạp

Bảng sau giả định mỗi phần tử số nguyên hoặc bản ghi cố định chiếm \(O(1)\) từ máy và nêu chi phí cho **một cách triển khai cụ thể**:

| Bài toán/cách triển khai | Thời gian tính/xuất mục | Bộ nhớ phụ | Kích thước kết quả hiện thực hóa |
|---|---|---|---|
| Tìm max của mảng \(n\) số bằng quét tuyến tính | \(\Theta(n)\) | \(O(1)\) | \(O(1)\) số |
| Tính mảng tổng tiền tố bằng một vòng lặp, trả mảng dài \(n+1\) | \(\Theta(n)\) | \(O(1)\) ngoài mảng trả về | \(\Theta(n)\) số |
| Tạo danh sách mọi cặp \(i<j\) | \(\Theta(n^2)\) lần tạo cặp | \(O(1)\) trạng thái vòng lặp, chưa tính cấp phát danh sách | \(\Theta(n^2)\) cặp |
| Phát mọi cặp \(i<j\) cho consumer xử lý ngay | \(\Theta(n^2)\) lần phát cặp | \(O(1)\) từ máy nếu consumer không giữ thêm trạng thái lớn | Không giữ trong nguồn; đầu ra bên ngoài vẫn có \(k=\Theta(n^2)\) cặp |
| Quay lui sinh mọi tập con và sao chép mỗi tập con vào kết quả | \(\Theta(n2^n)\) bước sao chép mục của kết quả | \(O(n)\) đường đi/ngăn xếp, không kể danh sách đầu ra | \(\Theta(n2^n)\) mục của các tập con |

Các cận bộ nhớ phụ trong bảng là **quy ước đã tách kết quả khỏi vùng làm việc**. Một triển khai dùng buffer phụ, ánh xạ dữ liệu, đệ quy sâu hơn hoặc đối tượng trung gian có thể cần nhiều RAM hơn. Cận thời gian “xuất mục” cũng chưa phản ánh đầy đủ chi phí chuyển các mục thành chuỗi dài và đẩy qua đường truyền chậm.

Không nên kết luận “thuật toán A tốt hơn B” chỉ từ một ô trong bảng: tùy giao diện cần danh sách hay luồng, yêu cầu truy cập ngẫu nhiên, bộ nhớ sẵn có và số lần dùng lại, trade-off sẽ khác nhau.

## 10. Đánh giá lý thuyết và đo thực tế

Để so sánh hai cách triển khai, cần giữ ổn định **đề bài và hợp đồng đầu ra**. Nếu một cách chỉ đếm, còn cách kia liệt kê, chúng giải những yêu cầu khác nhau. Nếu một cách chỉ khởi tạo Stream chưa tiêu thụ, còn cách kia đã dựng xong List, việc so thời gian đến lúc trả về sẽ không phản ánh tổng công việc.

Có thể đánh giá theo các bước:

1. **Kiểm tra tính đúng:** cùng đầu vào phải sinh đúng dữ liệu, số lượng, thứ tự và định dạng nếu hợp đồng yêu cầu; kiểm tra \(n=0\), \(n=1\), dữ liệu lớn và lỗi I/O.
2. **Phân tích kích thước đầu vào/đầu ra:** xác định \(n\), \(k\), số byte \(B_{\text{out}}\); tính cận dưới do dữ liệu phải đọc và phải ghi.
3. **Phân tích CPU và RAM riêng:** độ phức tạp bước, bộ nhớ phụ, dung lượng kết quả, peak và tổng cấp phát. Cần lưu ý cấu trúc mảng động và GC.
4. **Đo tài nguyên trong môi trường thực:** thời gian tổng (wall-clock), CPU, bộ nhớ heap đỉnh, lưu lượng ghi, dung lượng tệp, tốc độ xử lý và thời gian tới phần tử đầu tiên.
5. **Đo đầy đủ quá trình tiêu thụ:** với lazy/streaming, chạy đến khi hoàn tất nếu bài toán cần toàn bộ đầu ra; không chỉ đo bước tạo iterator hay Stream.
6. **Đánh giá ràng buộc hệ thống:** dung lượng RAM, kích thước tệp tối đa, bộ đệm, băng thông, thời gian chờ, trường hợp phía nhận chậm, khả năng hủy và retry.

Ví dụ, streaming có thể giảm peak heap nhưng tăng thời gian tổng nếu in từng dòng qua thiết bị chậm. Sử dụng bộ đệm ghi theo lô có thể tăng tốc độ thực tế với một lượng RAM hữu hạn; cả hai vẫn phải truyền đủ \(B_{\text{out}}\) byte nếu đặc tả đòi ghi hết. Độ phức tạp Big-O cho biết xu hướng tăng; benchmark đo hằng số, độ trễ và ảnh hưởng của môi trường.

## 11. Các sai lầm cần tránh

- **Gộp bộ nhớ phụ và đầu ra thành một con số mơ hồ:** ghi “space \(O(1)\)” cho thuật toán trả danh sách \(O(n^2)\) mà không nói đã loại output space.
- **Đếm vòng lặp nhưng quên thao tác sao chép hoặc định dạng:** một danh sách \(k\) chuỗi dài có thể tốn thời gian và byte nhiều hơn \(O(k)\).
- **Đồng nhất streaming với kết quả nhỏ:** streaming giới hạn số phần tử được giữ tại nguồn; tổng số mục và byte mà người dùng cần có thể vẫn rất lớn.
- **Coi khởi tạo lazy là đã hoàn thành công việc:** hãy đo đến khi tất cả kết quả cần thiết được tiêu thụ.
- **Bỏ qua bộ nhận:** callback, toList(), hệ thống log hoặc bộ đệm không giới hạn có thể âm thầm gom lại toàn bộ đầu ra.
- **Cho rằng mọi cận \(O(1)\) đều là 0 byte:** luôn có biến, đối tượng, buffer hoặc overhead; \(O(1)\) chỉ nói không tăng theo kích thước đầu vào trong mô hình đang dùng.
- **Nhầm tổng cấp phát với peak:** nhiều đối tượng tạm được tạo rồi thu gom có thể gây áp lực GC dù peak RAM vừa phải.
- **Tối ưu sai đặc tả:** thay danh sách đầy đủ bằng số đếm hoặc mô tả nén chỉ hợp lệ khi yêu cầu đầu ra cho phép.

## 12. Checklist đặc tả thuật toán và câu hỏi tự kiểm tra

Trước khi công bố độ phức tạp, hãy trả lời: **(a)** đầu vào có kích thước gì? **(b)** đầu ra gồm bao nhiêu phần tử và bao nhiêu byte? **(c)** phải giữ kết quả trong RAM hay có thể phát tuần tự? **(d)** bộ nhớ phụ đã bao gồm ngăn xếp đệ quy và cấu trúc trung gian chưa? **(e)** đã tính bước sao chép, in, mã hóa, ghi chưa? **(f)** có đảm bảo đầu ra đúng nội dung và định dạng yêu cầu không?

**Câu hỏi 1.** Một hàm tạo mảng dài \(n\) trong \(O(n)\) bước, ngoài mảng chỉ dùng biến i và sum. Bộ nhớ phụ là bao nhiêu và bộ nhớ kết quả là bao nhiêu?

**Đáp án:** \(O(1)\) bộ nhớ phụ theo quy ước loại trừ đầu ra; \(\Theta(n)\) phần tử cho mảng kết quả; tổng RAM khi mảng tồn tại là ít nhất \(\Omega(n)\).

**Câu hỏi 2.** Một thuật toán có thể sinh từng cặp chỉ số của \(n\) phần tử mà không lưu cặp trước đó. Có thể nói tổng thời gian liệt kê tất cả cặp là \(O(n)\) không?

**Đáp án:** Không. Có \(\frac{n(n-1)}{2}=\Theta(n^2)\) cặp; việc xuất từng cặp tường minh có cận dưới \(\Omega(n^2)\) bước theo mô hình một mục mỗi bước. Streaming chỉ giảm bộ nhớ giữ kết quả.

**Câu hỏi 3.** Hai thuật toán đều tạo \(k\) kết quả: A lưu mỗi kết quả bằng hai chỉ số, B sao chép toàn bộ nội dung chuỗi tương ứng. Vì sao số mục bằng nhau nhưng RAM và thời gian có thể khác nhau?

**Đáp án:** Chi phí phụ thuộc **kích thước biểu diễn từng mục** và lượng dữ liệu phải sao chép, không chỉ số mục. Với tất cả đoạn con của chuỗi dài \(n\), cặp chỉ số cần \(\Theta(n^2)\) mục, còn các bản sao ký tự có thể chứa \(\Theta(n^3)\) ký tự.

**Ghi nhớ:** Khi mô tả một thuật toán có đầu ra lớn, nên báo cáo ít nhất **thời gian sinh/ghi, bộ nhớ phụ và kích thước kết quả**. Điều này giúp lựa chọn giải pháp vừa **đúng yêu cầu đầu ra**, vừa phù hợp ngân sách CPU, RAM và I/O.