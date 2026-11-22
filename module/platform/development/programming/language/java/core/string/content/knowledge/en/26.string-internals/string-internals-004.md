# Bộ nhớ đệm `hashCode` của `String` là chi tiết cài đặt

## 1. Ý chính: giá trị băm là hợp đồng API, cách lưu đệm là nội bộ

`String` trong Java là kiểu **bất biến** (*immutable*): sau khi một đối tượng `String` được tạo, dãy ký tự của đối tượng đó không thay đổi. Vì thế, giá trị `hashCode()` tính từ nội dung của cùng một `String` luôn ổn định.

Cần phân biệt hai điều:

1. **Hợp đồng được Java công khai:** `String.hashCode()` phải tính hash theo công thức đã ghi trong tài liệu API. Hai chuỗi có nội dung bằng nhau theo `equals` phải có cùng hash; chuỗi rỗng có hash bằng `0`. Chương trình được phép dựa vào các tính chất này.
2. **Cách JDK tối ưu phép tính:** Một số triển khai, như OpenJDK 17, lưu kết quả hash đã tính trong các trường riêng của đối tượng để tránh phải quét lại ký tự. Cấu trúc trường, điều kiện cache, thời điểm lưu và cách đồng bộ là **chi tiết cài đặt**. Chương trình ứng dụng không nên phụ thuộc vào chúng.

Nói cách khác, kết quả `s.hashCode()` được xác định bởi *nội dung* của `s` và hợp đồng API, không phải bởi việc JVM có dùng bộ nhớ đệm hay không. Việc có cache cũng không biến `hashCode()` thành hàm định danh đối tượng hoặc hàm băm mật mã.

## 2. Công thức chính thức của `String.hashCode()`

Tài liệu Java định nghĩa hash cho chuỗi gồm `n` đơn vị ký tự `char` là:

```text
h = s[0] × 31^(n-1) + s[1] × 31^(n-2) + ... + s[n-1]
```

Phép tính sử dụng kiểu `int` 32-bit của Java. Viết dưới dạng vòng lặp tương đương:

```java
static int calculateHash(String text) {
    int h = 0;
    for (int i = 0; i < text.length(); i++) {
        h = 31 * h + text.charAt(i);
    }
    return h;
}
```

Đây là **phương thức minh họa** có thể đặt vào một lớp Java; nó thể hiện công thức, không mô phỏng cơ chế cache của `String`.

- `s.charAt(i)` truy cập một **UTF-16 code unit**; các ký tự ngoài BMP (ví dụ nhiều emoji) được biểu diễn bằng hai `char` và cả hai tham gia phép băm.
- `int` có thể tràn; Java dùng phép toán số nguyên 32-bit với phần bit thấp được giữ lại. Không thêm `long` hoặc cách xử lý overflow khác nếu muốn tính đúng hash chuẩn của `String`.
- Với chuỗi rỗng, không có lần lặp nào, nên kết quả là `0`.
- Công thức phụ thuộc vào thứ tự và giá trị các `char`, không phụ thuộc vào charset mã hóa file, encoding của terminal, địa chỉ đối tượng hay cách JVM lưu chuỗi trong bộ nhớ.
- Giá trị có thể âm vì kết quả được diễn giải như `int` có dấu. Hash không phải một số thứ tự hay ID duy nhất.

Ví dụ, `"Aa"` và `"BB"` có hash giống nhau:

```text
"Aa": 65 × 31 + 97 = 2112
"BB": 66 × 31 + 66 = 2112
```

Hai chuỗi này **khác nội dung** dù có cùng `hashCode()`. Đây là *va chạm hash* (*hash collision*), không phải lỗi của Java.

## 3. Cache hoạt động như thế nào trong một triển khai cụ thể?

Một cách triển khai tối ưu phổ biến của `String.hashCode()` là:

1. Nếu đã lưu được hash cho chính đối tượng `String` hiện tại, trả lại giá trị đã lưu.
2. Nếu chưa có kết quả được lưu, tính hash theo công thức chuẩn.
3. Có thể ghi kết quả vào một trường riêng để những lần gọi sau không phải duyệt lại chuỗi.

Vì `String` bất biến nên kết quả không cần bị vô hiệu hóa khi nội dung “thay đổi”: muốn tạo nội dung khác thì Java tạo ra một kết quả kiểu `String` khác (trừ những tối ưu trả lại cùng đối tượng khi nội dung không thay đổi). Thao tác như `concat`, `replace`, `substring` không cho phép sửa ký tự trực tiếp trong đối tượng gốc.

**Ví dụ cụ thể của OpenJDK 17:** mã nguồn lớp `java.lang.String` có các trường riêng `hash` (kiểu `int`) và `hashIsZero` (kiểu `boolean`). Khi cần, `hashCode()` có thể tính hash dựa trên cách mã hóa nội bộ rồi lưu kết quả. Nếu hash thật bằng `0`, cờ `hashIsZero` giúp phân biệt trường hợp “đã tính và bằng 0” với “chưa có giá trị hash được lưu” mà không cần quét lại chuỗi.

Chi tiết này nhằm giải thích *vì sao có thể tối ưu*, không phải lời hứa rằng mọi JDK, mọi bản phát hành hoặc mọi đường đi của JVM đều có hai trường mang đúng những tên đó. Trong các bản OpenJDK cũ hơn, xử lý hash bằng `0` từng khác; triển khai trong tương lai cũng có thể đổi.

**Lưu ý về hash bằng 0:** `0` hoàn toàn là kết quả hợp lệ, không tự động có nghĩa “chưa được cache”. Cả `""` lẫn chuỗi gồm một ký tự NUL (`"\0"`) đều có hash bằng `0`. Do đó, tuyệt đối không suy luận rằng những chuỗi có hash `0` luôn được tính lại hoặc luôn đã lưu vào bộ nhớ đệm.

Không nên viết mã reflection để đọc/sửa các trường riêng như `hash`, `hashIsZero` hoặc `value`. Chúng không thuộc API công khai, có thể bị module system ngăn truy cập và việc can thiệp có nguy cơ phá vỡ hành vi của các cấu trúc dùng khóa chuỗi.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu thành file **`StringHashCodeDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public class StringHashCodeDemo {
    private static int calculateHash(String text) {
        int h = 0;
        for (int i = 0; i < text.length(); i++) {
            h = 31 * h + text.charAt(i);
        }
        return h;
    }

    public static void main(String[] args) {
        String first = "Aa";
        String second = "BB";
        String equalCopy = new String(new char[] {'A', 'a'});

        System.out.println("Aa hash: " + first.hashCode());
        System.out.println("BB hash: " + second.hashCode());
        System.out.println("Aa equals BB: " + first.equals(second));
        System.out.println("Equal text, same hash: "
                + (first.hashCode() == equalCopy.hashCode()));
        System.out.println("Different objects: " + (first != equalCopy));

        System.out.println("Empty hash: " + "".hashCode());
        System.out.println("NUL hash: " + "\0".hashCode());
        System.out.println("Formula matches: "
                + (calculateHash(first) == first.hashCode()));

        Map<String, Integer> map = new HashMap<>();
        map.put(first, 1);
        map.put(second, 2);

        System.out.println("Map size: " + map.size());
        System.out.println("Map Aa: " + map.get("Aa"));
        System.out.println("Map BB: " + map.get("BB"));

        String changed = first.concat("!");
        System.out.println("Original: " + first);
        System.out.println("Concatenated: " + changed);
    }
}
```

Biên dịch và chạy:

```bash
javac StringHashCodeDemo.java
java StringHashCodeDemo
```

**Stdout chính xác** theo hợp đồng Java 17+:

```text
Aa hash: 2112
BB hash: 2112
Aa equals BB: false
Equal text, same hash: true
Different objects: true
Empty hash: 0
NUL hash: 0
Formula matches: true
Map size: 2
Map Aa: 1
Map BB: 2
Original: Aa
Concatenated: Aa!
```

Diễn giải:

- `first.hashCode()` và `second.hashCode()` đều bằng `2112` nhưng `first.equals(second)` là `false`: cùng hash không có nghĩa là cùng chuỗi.
- `equalCopy` được tạo từ một mảng `char` mới, nên là đối tượng khác `first` nhưng có cùng nội dung; vì thế hash của hai đối tượng bằng nhau.
- Chuỗi rỗng và chuỗi chứa ký tự NUL đều có hash bằng `0`. Output này **không cho biết** triển khai hiện tại có cache kết quả `0` hay không.
- `calculateHash(first)` cho kết quả giống `first.hashCode()` mà không dùng một trường cache nào. Điều này minh họa kết quả theo đặc tả, không kiểm tra cấu trúc dữ liệu nội bộ của JDK.
- `HashMap` vẫn giữ cả hai khóa `"Aa"` và `"BB"` vì ngoài hash, cơ chế so sánh khóa còn xét quan hệ bằng nhau khi cần.
- `concat("!")` tạo chuỗi có nội dung mới; biến `first` vẫn tham chiếu đến giá trị `"Aa"` ban đầu. Do đó, hash của đối tượng gốc không phải được “cập nhật để theo nội dung mới”.

**Không thể chứng minh cache bằng một đoạn code chỉ in giá trị `hashCode()`.** Một triển khai luôn tính lại hash và một triển khai có cache vẫn phải cho cùng các kết quả trên.

## 5. Chi phí tính toán và giới hạn của tối ưu hóa cache

Nếu tính lại công thức bằng cách đi qua `n` code unit thì số bước tỷ lệ với chiều dài chuỗi: **O(n)**. Với chiến lược cache, lần tính đầu có thể là O(n), còn lần đọc lại một giá trị đã lưu thường là **O(1)** về mặt số thao tác với dữ liệu chuỗi.

Đây là mô hình giải thích một tối ưu khả dĩ, **không phải cam kết độ phức tạp cho mọi lần gọi** của mọi triển khai `String.hashCode()`. Kết quả thực tế còn chịu ảnh hưởng của JIT, escape analysis, constant folding, độ dài chuỗi, việc đối tượng có dùng lại hay không và cách triển khai JVM.

| Tình huống | Điều có thể kỳ vọng về mặt ứng dụng |
| --- | --- |
| Gọi `hashCode()` nhiều lần trên cùng đối tượng `String` | Luôn nhận cùng giá trị; JDK có thể tận dụng giá trị đã tính. |
| Tạo rất nhiều đối tượng `String` bằng nhau về nội dung | Mỗi đối tượng vẫn có trạng thái nội bộ riêng; không được giả định mọi đối tượng chia sẻ cùng cache. |
| Hash bằng `0` | Kết quả là `0`; việc tránh tính lại tùy triển khai. |
| Thay đổi cách lưu chuỗi giữa các phiên bản JDK | Công thức và kết quả công khai phải giữ nguyên; kỹ thuật lưu byte và cache có thể khác. |
| Gọi `hashCode()` từ nhiều thread | Mọi lời gọi phải trả kết quả đúng; không được dựa vào việc hash chỉ được tính một lần. |

Khi đánh giá hiệu năng, cần đo **ứng dụng thật** bằng phương pháp benchmark phù hợp như JMH. Không nên kết luận dựa trên `System.nanoTime()` quanh một hoặc vài lần gọi `hashCode()`, vì mã có thể được JIT tối ưu, loại bỏ phép tính hoặc thay đổi theo warm-up.

## 6. Thread safety: vì sao trường cache không nhất thiết phải là `final`?

`String` có nội dung bất biến, nhưng một triển khai có thể **lưu trạng thái tính toán nội bộ** vào trường cache sau khi khởi tạo đối tượng. “Bất biến” của `String` ở cấp API nói về nội dung ký tự quan sát được, không bắt buộc tất cả bit trong bộ nhớ đối tượng đều bất biến sau constructor.

Trong OpenJDK 17, phần tối ưu hash được thiết kế để các lần gọi đồng thời có thể đọc hoặc ghi cache mà không cần khóa tường minh. Nếu hai thread cùng lần đầu gọi `hashCode()`, một số phép tính có thể bị lặp lại. Do phép tính băm dựa trên nội dung bất biến, kết quả công khai vẫn như nhau. Mã nguồn OpenJDK mô tả trường hợp này là một kiểu *benign data race* với những ràng buộc cụ thể để giữ kết quả đúng.

Nhận định trên chỉ áp dụng cho thiết kế được kiểm soát trong `String`, **không phải khuyến nghị chung** rằng lập trình viên có thể thoải mái đặt các trường cache có data race trong đối tượng do mình viết. Với lớp mutable hoặc phép tính có side effect, cache thiếu đồng bộ có thể dẫn đến lỗi hoặc dữ liệu không nhất quán.

Ứng dụng nhiều thread có thể gọi `hashCode()` trên cùng một `String` bình thường; không cần tự khóa chuỗi để bảo vệ cache nội bộ. Tuy nhiên, **không được dùng số lần tính hash, số lần ghi trường cache hoặc trạng thái cache làm cơ chế giao tiếp giữa các thread**.

## 7. Liên hệ với `equals`, `HashMap` và bộ nhớ

Hợp đồng liên quan:

- Nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` phải là `true`.
- Nếu hai hash bằng nhau thì **không suy ra** `equals` là `true`.
- `String.equals` so sánh nội dung; toán tử `==` so sánh tham chiếu. Tối ưu cache hash không thay đổi hai quy tắc này.
- `HashMap` và `HashSet` dùng hash để hỗ trợ tìm bucket/vị trí tra cứu và dùng quan hệ bằng nhau để phân biệt khóa khi cần. `HashMap` còn có thể trộn bit hash trong triển khai riêng; cấu trúc bucket không phải một phần của hợp đồng `String.hashCode()`.
- `String.hashCode()` **không dùng để mã hóa an toàn**, kiểm tra tính toàn vẹn chống sửa đổi hay lưu mật khẩu. Hash 32-bit dễ va chạm và dự đoán được; nếu cần mật mã, dùng API và thuật toán bảo mật phù hợp.

Một số chi tiết riêng tư của OpenJDK còn liên quan đến *Compact Strings*: từ JDK 9, nhiều chuỗi được lưu hiệu quả bằng mảng byte và thông tin biểu diễn Latin-1/UTF-16 thay vì luôn dùng mảng `char` như trước. Cách lưu này có thể ảnh hưởng chi phí bộ nhớ và đường tính toán, nhưng **không đổi công thức hash theo các UTF-16 code unit logic**. Vì vậy, không suy kích thước đối tượng hoặc số byte cache từ công thức hash; chúng phụ thuộc phiên bản JDK, JVM và cấu hình.

Có trường cache cũng không đồng nghĩa với việc mọi `String` lập tức tốn chi phí quét ký tự tính hash. Một triển khai có thể tính **lười** (*lazy*) khi hash được yêu cầu; việc có hay chưa có giá trị lưu là trạng thái nội bộ. Mã ứng dụng chỉ nên dựa vào dữ liệu công khai: chuỗi, kết quả `equals` và `hashCode()`.

## 8. Sai lầm thường gặp và cách tránh

**Sai lầm 1: “`String.hashCode()` nhanh O(1) trên mọi lần gọi vì Java luôn cache.”**

Điều đúng là một triển khai có thể cache và lần đọc cache thường rẻ. Đặc tả không yêu cầu cấu trúc cache cụ thể; không thể đảm bảo lần gọi đầu, hai thread cùng gọi hoặc mọi JVM đều chỉ phải làm một lượng việc cố định.

**Sai lầm 2: “Nếu hash bằng `0` thì chưa tính.”**

`0` là giá trị hash hợp lệ, ví dụ `""` và `"\0"`. Một số bản OpenJDK có cờ riêng đánh dấu hash đã tính bằng `0`. Không suy đoán cache chỉ từ giá trị trả về.

**Sai lầm 3: “Hai chuỗi có hash giống nhau là cùng nội dung.”**

`"Aa"` và `"BB"` đều có hash `2112` nhưng không bằng nhau. Khi cần kiểm tra nội dung, dùng `equals`; không thay bằng so sánh `hashCode()`.

**Sai lầm 4: “Muốn tối ưu, sửa trường `hash` bằng reflection.”**

Trường riêng thuộc triển khai nội bộ; can thiệp phá vỡ tính nhất quán và có thể không thực hiện được do kiểm soát truy cập của module system. Không phụ thuộc vào layout đối tượng.

**Sai lầm 5: “Cache hash đồng nghĩa String có thể bị đổi nội dung.”**

Cache chỉ ghi lại kết quả tính toán, không thay đổi các ký tự của `String`. Các thao tác tạo nội dung khác không chỉnh trực tiếp chuỗi gốc.

**Sai lầm 6: “Có thể nhìn thời gian một lần gọi để xác định chắc chắn cache.”**

JIT, inlining, constant folding, warm-up và benchmark sai cách có thể làm phép đo vô nghĩa. Không dùng thời gian đo thô như bằng chứng về cấu trúc nội bộ.

## 9. Quy tắc áp dụng trong mã Java

1. Dùng `String.hashCode()` bình thường khi API thu thập hoặc cấu trúc dữ liệu cần hash; không tự tính lại hoặc tự cache trừ khi có lý do nghiệp vụ/đo đạc rõ ràng.
2. Dùng `equals` để xác định nội dung bằng nhau; dùng `==` chỉ khi thật sự cần kiểm tra cùng tham chiếu.
3. Khi dùng `String` làm khóa `HashMap`/`HashSet`, có thể dựa vào tính bất biến và hợp đồng `equals`/`hashCode`, không dựa vào cơ chế cache của một bản JDK.
4. Chấp nhận hash collision như hiện tượng bình thường. Đừng sử dụng hash làm ID duy nhất, dấu vân tay mật mã hoặc thay thế toàn bộ dữ liệu gốc.
5. Khi đọc mã nguồn JDK để học tối ưu, phân biệt rõ **“OpenJDK phiên bản X thực hiện như thế nào”** với **“Java SE API cam kết điều gì”**.

## Tài liệu tham khảo

- [Java SE 17 — `String.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode()) — nguồn chính thức của công thức và giá trị hash.
- [Java SE 17 — `Object.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()) — hợp đồng chung giữa hash và equality.
- [OpenJDK 17 — mã nguồn `java.lang.String`](https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/lang/String.java) — ví dụ cụ thể về trường `hash`/`hashIsZero` và cách tối ưu; đây là phần triển khai, không phải API công khai.
