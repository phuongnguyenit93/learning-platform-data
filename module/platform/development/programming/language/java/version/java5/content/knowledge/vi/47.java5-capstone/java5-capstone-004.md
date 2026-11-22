# Xây dựng bộ tùy chọn bằng EnumSet

## 1. Bài toán: nhiều tính năng có thể bật cùng lúc

Cần tạo bộ tùy chọn cho một hàm dựng báo cáo văn bản:

- Có hoặc không có tiêu đề.
- Đánh số các dòng được xuất.
- Bỏ qua dòng trống.
- Chuyển nội dung thành chữ hoa.

Đây là các khả năng có thể kết hợp. Một báo cáo có thể vừa có tiêu đề, vừa đánh số, vừa bỏ dòng trống. Nếu truyền bốn tham số boolean, lời gọi như `render(data, true, false, true, true)` khó đọc và dễ đảo vị trí.

Ta sẽ đặt tên cho từng tùy chọn bằng một enum, rồi dùng `EnumSet` để biểu diễn tập tùy chọn đang bật.

Yêu cầu của bài thực hành:

1. Các tùy chọn phải thuộc cùng một kiểu enum.
2. Tập rỗng là cấu hình hợp lệ.
3. Thêm một tùy chọn hai lần không tạo bản sao.
4. Không để người gọi sửa lén cấu hình qua tập đầu vào hoặc giá trị trả về.
5. Mã tùy chọn từ cấu hình bên ngoài phải được phân tích và kiểm tra rõ ràng.
6. Có chương trình Java 17+ chạy đầy đủ và kết quả kiểm chứng được.

## 2. Vì sao EnumSet phù hợp?

`EnumSet<E>` là một triển khai `Set` chuyên dành cho phần tử enum. Nó lưu tập hợp tùy chọn, không lưu số lần một tùy chọn xuất hiện.

Đặc điểm quan trọng:

- Một tập chỉ chứa hằng của cùng một kiểu enum.
- Không chấp nhận phần tử `null`.
- Thứ tự duyệt theo thứ tự khai báo hằng enum, không theo thứ tự thêm.
- Là tập có thể thay đổi và không tự đồng bộ cho nhiều luồng.

Bên trong, `EnumSet` dùng biểu diễn vector bit. Điều đó không có nghĩa mã ứng dụng phải tự dịch bit bằng `ordinal()`, hoặc chỉ được dùng tối đa 64 hằng. Hãy dùng API tập hợp thay vì phụ thuộc cấu trúc triển khai cụ thể.

Hợp đồng này được định nghĩa trong [EnumSet API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html).

So sánh các lựa chọn:

| Cách biểu diễn | Khi phù hợp |
| --- | --- |
| Một enum đơn lẻ | Chỉ có đúng một chế độ tại một thời điểm |
| `EnumSet<Option>` | Nhiều tùy chọn enum có thể cùng bật |
| Đối tượng cấu hình có nhiều trường | Tùy chọn còn có giá trị, ví dụ độ rộng, số lần thử hoặc đường dẫn |
| `EnumMap<Option, Value>` | Mỗi hằng enum gắn với một giá trị cùng kiểu |

Không biến mọi cấu hình thành cờ. Chẳng hạn, chế độ chữ “giữ nguyên / chữ hoa / chữ thường” có thể là một enum đơn lẻ nếu phải chọn đúng một, thay vì ba cờ mâu thuẫn trong cùng tập.

## 3. Xác định ý nghĩa tập rỗng và cấu hình mặc định

Tập rỗng phải có nghĩa cụ thể. Trong bài này:

```text
Không có tùy chọn
→ không thêm tiêu đề
→ không đánh số
→ giữ dòng trống
→ giữ nguyên nội dung
```

“Tập rỗng” không tự có nghĩa “dùng tất cả mặc định”. Nếu API muốn mặc định riêng, nên có factory mang tên rõ ràng như `defaults()`, thay vì âm thầm diễn giải lại mọi tập rỗng.

Một cách tạo:

```java
EnumSet<ReportOption> none =
        EnumSet.noneOf(ReportOption.class);

EnumSet<ReportOption> selected =
        EnumSet.of(ReportOption.HEADER, ReportOption.NUMBER_LINES);
```

`EnumSet` là lớp trừu tượng có các phương thức tạo; không dùng `new EnumSet<>()`.

Có thể tạo tất cả tùy chọn:

```java
EnumSet<ReportOption> all =
        EnumSet.allOf(ReportOption.class);
```

Nhưng không nên lấy `allOf()` làm mặc định nếu việc thêm một hằng mới trong phiên bản sau không được phép tự bật tính năng đó. Mặc định là quyết định hành vi của API, không phải hệ quả bắt buộc của tập hợp.

## 4. Các phép toán tập hợp cho bộ tùy chọn

```java
EnumSet<ReportOption> selected =
        EnumSet.of(ReportOption.HEADER);

selected.add(ReportOption.NUMBER_LINES);
selected.add(ReportOption.NUMBER_LINES); // Không tạo phần tử trùng.
selected.remove(ReportOption.HEADER);

boolean numbered = selected.contains(ReportOption.NUMBER_LINES);
```

Các phép toán kết hợp:

| API | Ý nghĩa |
| --- | --- |
| `addAll(other)` | Bật thêm các tùy chọn từ tập khác |
| `removeAll(other)` | Tắt những tùy chọn nằm trong tập khác |
| `retainAll(other)` | Chỉ giữ các tùy chọn chung |
| `containsAll(required)` | Kiểm tra đã bật toàn bộ tập yêu cầu chưa |
| `complementOf(set)` | Tạo tập các hằng cùng enum chưa nằm trong tập đã cho |
| `clone()` | Tạo tập mới có cùng phần tử |

Các phương thức thay đổi như `retainAll()` tác động lên tập nhận lời gọi. Nếu cần giữ cấu hình ban đầu, phải sao chép trước.

`range(from, to)` chọn theo khoảng thứ tự khai báo. Không dùng nó để mã hóa một nhóm nghiệp vụ nếu sau này việc chèn hằng vào giữa sẽ làm nhóm tự thay đổi. Với một nhóm hành vi cụ thể, liệt kê bằng `of(...)` thường rõ ràng hơn.

## 5. Bẫy copyOf với collection rỗng

Hai lời gọi sau không có cùng điều kiện:

```java
EnumSet<ReportOption> typedEmpty =
        EnumSet.noneOf(ReportOption.class);
EnumSet<ReportOption> copied =
        EnumSet.copyOf(typedEmpty); // Hợp lệ dù rỗng.
```

```java
// Ví dụ lỗi runtime có chủ đích.
EnumSet<ReportOption> copied =
        EnumSet.copyOf(List.<ReportOption>of());
```

Ở trường hợp thứ hai, đối số là collection rỗng thông thường, không cung cấp thông tin runtime để suy ra enum cụ thể; `copyOf(Collection)` báo `IllegalArgumentException`. Kiểu generic ghi ở mã nguồn không thay thế thông tin enum cần lúc chạy.

Một factory nhận collection tùy ý và cho phép rỗng nên làm như sau:

```java
EnumSet<ReportOption> copy =
        EnumSet.noneOf(ReportOption.class);
copy.addAll(input);
```

Đây là lý do lời giải dùng `noneOf()` rồi `addAll()`, thay vì gọi `copyOf()` không xét trường hợp rỗng. Việc chấp nhận rỗng không có nghĩa chấp nhận phần tử `null`.

## 6. Bảo vệ cấu hình khỏi thay đổi ngoài ý muốn

Một `EnumSet` vẫn là tập mutable. Nếu constructor giữ trực tiếp tập người gọi truyền vào, người gọi có thể sửa cấu hình sau khi tạo mà không thông qua API.

Tương tự, getter trả trực tiếp trường `EnumSet` nội bộ làm lộ quyền thay đổi.

Bài này chọn mô hình:

```text
Đầu vào được sao chép
        |
Cấu hình giữ một tập riêng không sửa sau khởi tạo
        |
with()/without() tạo cấu hình mới
        |
asSet() trả bản sao không cho sửa
```

`Collections.unmodifiableSet(original)` chỉ tạo một khung nhìn không cho sửa **qua tham chiếu đó**. Nếu ai còn giữ `original` và sửa nó, khung nhìn vẫn phản ánh thay đổi. Vì vậy, lời giải bọc một bản `clone()` tách biệt. Xem [Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)).

Cũng có thể dùng `Set.copyOf()` khi chỉ cần tập không sửa được, nhưng API đó không cam kết giữ thứ tự duyệt của `EnumSet`. Trong bài, giữ thứ tự khai báo giúp kết quả hiển thị ổn định; hợp đồng tập không sửa được được mô tả trong [Set API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html).

## 7. Lời giải Java 17+ chạy đầy đủ

Quy ước dựng báo cáo:

- Tiêu đề là `REPORT` và không nằm trong số dòng nội dung.
- Khi bỏ dòng trống, số thứ tự được tính trên các dòng thực sự được xuất.
- Chữ hoa dùng `Locale.ROOT` để hành vi không phụ thuộc locale mặc định của máy.
- Không chấp nhận dòng đầu vào `null`.
- Tùy chọn từ chuỗi dùng mã ổn định riêng, không dùng vị trí hằng enum.

Lưu thành `EnumSetOptionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class EnumSetOptionsDemo {
    enum ReportOption {
        HEADER("header"),
        NUMBER_LINES("numbers"),
        SKIP_BLANK_LINES("skip-blank"),
        UPPERCASE("uppercase");

        private final String token;

        ReportOption(String token) {
            this.token = token;
        }

        static ReportOption parse(String token) {
            Objects.requireNonNull(token);
            for (ReportOption option : values()) {
                if (option.token.equals(token)) {
                    return option;
                }
            }
            throw new IllegalArgumentException("Unknown option token");
        }
    }

    static final class ReportOptions {
        private final EnumSet<ReportOption> enabled;

        private ReportOptions(EnumSet<ReportOption> enabled) {
            this.enabled = enabled.clone();
        }

        static ReportOptions from(Collection<ReportOption> input) {
            Objects.requireNonNull(input);
            EnumSet<ReportOption> copy =
                    EnumSet.noneOf(ReportOption.class);
            copy.addAll(input);
            return new ReportOptions(copy);
        }

        static ReportOptions parseTokens(Collection<String> tokens) {
            Objects.requireNonNull(tokens);
            EnumSet<ReportOption> result =
                    EnumSet.noneOf(ReportOption.class);
            for (String token : tokens) {
                result.add(ReportOption.parse(token));
            }
            return new ReportOptions(result);
        }

        boolean has(ReportOption option) {
            return enabled.contains(Objects.requireNonNull(option));
        }

        ReportOptions with(ReportOption option) {
            EnumSet<ReportOption> copy = enabled.clone();
            copy.add(Objects.requireNonNull(option));
            return new ReportOptions(copy);
        }

        ReportOptions without(ReportOption option) {
            EnumSet<ReportOption> copy = enabled.clone();
            copy.remove(Objects.requireNonNull(option));
            return new ReportOptions(copy);
        }

        Set<ReportOption> asSet() {
            return Collections.unmodifiableSet(enabled.clone());
        }
    }

    static String render(List<String> input, ReportOptions options) {
        Objects.requireNonNull(input);
        Objects.requireNonNull(options);
        List<String> output = new ArrayList<>();
        if (options.has(ReportOption.HEADER)) {
            output.add("REPORT");
        }

        int number = 0;
        for (String original : input) {
            Objects.requireNonNull(original);
            if (options.has(ReportOption.SKIP_BLANK_LINES)
                    && original.isBlank()) {
                continue;
            }
            String line = options.has(ReportOption.UPPERCASE)
                    ? original.toUpperCase(Locale.ROOT) : original;
            if (options.has(ReportOption.NUMBER_LINES)) {
                line = ++number + ": " + line;
            }
            output.add(line);
        }
        return String.join("\n", output);
    }

    public static void main(String[] args) {
        EnumSet<ReportOption> callerOwned = EnumSet.of(
                ReportOption.NUMBER_LINES,
                ReportOption.HEADER,
                ReportOption.SKIP_BLANK_LINES);
        ReportOptions base = ReportOptions.from(callerOwned);
        callerOwned.clear();
        System.out.println("config=" + base.asSet());

        ReportOptions uppercase = base.with(ReportOption.UPPERCASE);
        System.out.println("originalHasUppercase="
                + base.has(ReportOption.UPPERCASE));
        System.out.println("copyHasUppercase="
                + uppercase.has(ReportOption.UPPERCASE));
        System.out.println(render(List.of("alpha", "", "beta"), uppercase));

        try {
            base.asSet().add(ReportOption.UPPERCASE);
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshotMutation=REJECTED");
        }

        System.out.println("empty="
                + ReportOptions.parseTokens(List.of()).asSet());
        try {
            ReportOptions.parseTokens(List.of("unknown"));
        } catch (IllegalArgumentException expected) {
            System.out.println("unknown=REJECTED");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -Xlint:all -Werror EnumSetOptionsDemo.java
java EnumSetOptionsDemo
```

Stdout:

```text
config=[HEADER, NUMBER_LINES, SKIP_BLANK_LINES]
originalHasUppercase=false
copyHasUppercase=true
REPORT
1: ALPHA
2: BETA
snapshotMutation=REJECTED
empty=[]
unknown=REJECTED
```

### Đọc bằng chứng từ kết quả

`callerOwned.clear()` không làm cấu hình `base` mất tùy chọn vì API đã sao chép đầu vào.

`base.with(UPPERCASE)` tạo một cấu hình khác. Dòng `originalHasUppercase=false` cho thấy cấu hình ban đầu không đổi.

Tập được in theo `HEADER`, `NUMBER_LINES`, `SKIP_BLANK_LINES` dù thứ tự thêm trong `main()` khác. Đó là thứ tự khai báo enum.

Thử sửa `asSet()` bị từ chối. Đây là lỗi runtime đúng chủ đích của tập không sửa được, không phải lỗi tương thích kiểu.

`parseTokens(List.of())` tạo cấu hình rỗng hợp lệ. Một mã ngoài danh sách được nhận diện bị từ chối, không bị âm thầm bỏ qua.

## 8. Phân tích chuỗi cấu hình mà không phụ thuộc ordinal

Trong enum của ví dụ, mỗi hằng có mã như `"header"` hoặc `"skip-blank"`. Đó là hợp đồng cấu hình bên ngoài, có thể được giữ ổn định khi đổi tên hằng Java.

Không lưu tùy chọn ra tệp hoặc cơ sở dữ liệu bằng `ordinal()`. Giá trị ordinal là vị trí khai báo, có thể thay đổi khi thêm hoặc sắp xếp lại hằng. API của [Enum.ordinal()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#ordinal()) mô tả nó phục vụ cấu trúc dữ liệu enum chuyên biệt như EnumSet.

Cũng không lấy chuỗi `toString()` của cả tập làm định dạng lưu trữ. Nó hữu ích để xem khi học hoặc chẩn đoán, nhưng định dạng cấu hình cần quy tắc riêng về mã, thứ tự, mục trùng và mã không nhận diện.

Chính sách phân tích trong bài là:

- Mã phân biệt chữ hoa/thường và phải khớp chính xác.
- Mã lặp chỉ bật tùy chọn một lần.
- Mã không nhận diện làm cấu hình thất bại.
- Không có mã nghĩa là không bật tùy chọn nào.

Nếu ứng dụng chọn chuẩn hóa khoảng trắng/chữ hoa, phải ghi rõ và kiểm thử; không thêm chuẩn hóa tùy tiện làm hai mã có ý nghĩa khác nhau bị nhập một.

## 9. EnumSet không tự xác minh mọi kết hợp nghiệp vụ

Trong ví dụ, bốn tùy chọn độc lập nên có thể kết hợp. Với hệ thống khác, một số cờ có thể không tương thích hoặc có điều kiện phụ thuộc.

Ví dụ, nếu thêm hai tùy chọn trái ngược “chỉ chữ hoa” và “chỉ chữ thường”, có hai cách thiết kế:

1. Tách thành một trường `LetterCase` có ba lựa chọn loại trừ nhau.
2. Nếu vẫn dùng tập, kiểm tra và từ chối tổ hợp không hợp lệ ở nơi tạo cấu hình.

Không để mỗi hàm sử dụng tự quyết định một cách khác nhau khi có xung đột. Nên chuẩn hóa/kiểm tra cấu hình một lần trước khi thực thi hành vi.

Một tùy chọn cần tham số như “độ rộng dòng = 80” cũng nên có trường giá trị riêng; EnumSet chỉ mô tả sự có mặt của hằng, không lưu số 80 cho hằng đó.

## 10. Nhiều luồng và sự phát triển của enum

`EnumSet` không tự đồng bộ. Iterator không ném `ConcurrentModificationException` cũng không chứng minh có thể sửa đồng thời an toàn; không dùng việc “không thấy ngoại lệ” làm kiểm tra thread safety.

Lời giải giảm nhu cầu khóa bằng cấu hình không thay đổi sau khởi tạo, trường nội bộ không bị lộ và phương thức cập nhật tạo đối tượng mới. Khi chia sẻ cấu hình giữa các luồng, vẫn cần công bố tham chiếu theo cách an toàn của ứng dụng; nguồn collection không được sửa đồng thời trong lúc factory đang sao chép nó.

Khi thêm hằng mới, cần rà lại:

- Cấu hình mặc định có vô tình bật nó qua `allOf()` không?
- Các nhóm tạo bằng `range()` hoặc `complementOf()` có đổi nghĩa không?
- Bộ phân tích có mã ổn định và chính sách tương thích không?
- Hành vi dựng báo cáo có xử lý tùy chọn mới không?
- Các trường hợp kiểm thử có bao quát tổ hợp liên quan không?

Một kiểu enum tăng thêm hằng có thể tác động nhiều chỗ dù mã nguồn ở chỗ gọi không đổi. Đó là thay đổi hợp đồng hành vi cần được xét cùng thiết kế tập tùy chọn.

## 11. Bài tập mở rộng và tiêu chí kiểm tra

Thực hiện lần lượt:

1. Thêm `defaults()` bằng danh sách `of(...)` tường minh; kiểm tra khác biệt giữa mặc định và tập rỗng.
2. Dùng `without(NUMBER_LINES)` để tạo báo cáo không số từ cấu hình đang có; chứng minh cấu hình ban đầu không đổi.
3. Viết hàm xuất danh sách mã cấu hình theo thứ tự khai báo, rồi phân tích lại và so sánh tập kết quả.
4. Kiểm tra mã trùng, mã sai, collection rỗng và phần tử `null`.
5. Nếu thêm tùy chọn phụ thuộc/xung đột, đặt kiểm tra ở nơi tạo cấu hình và bổ sung ca từ chối.
6. Tách kiểu định dạng loại trừ nhau thành enum đơn lẻ nếu nó không phù hợp mô hình cờ.

Tiêu chí đạt:

- Lời giải biên dịch sạch mà không dùng kiểu thô.
- Hành vi bật/tắt được kiểm chứng qua đầu ra.
- Thay đổi tập đầu vào không làm cấu hình đổi.
- Không lộ tập nội bộ có thể sửa.
- Tập rỗng có ý nghĩa và không gây lỗi suy ra kiểu enum.
- Định dạng lưu cấu hình không phụ thuộc ordinal.

## 12. Tự kiểm tra

1. Vì sao EnumSet phù hợp hơn một enum đơn lẻ trong bài này? **Nhiều tùy chọn có thể cùng bật.**
2. Thứ tự duyệt dựa vào đâu? **Thứ tự khai báo các hằng enum.**
3. EnumSet có tự trở thành bất biến khi trường chứa nó là final không? **Không; final giữ tham chiếu, không cấm sửa tập.**
4. Vì sao copyOf một collection rỗng thông thường có thể lỗi? **Không suy ra được kiểu enum cần dùng lúc chạy.**
5. Chỉ bọc unmodifiableSet có đủ để tránh mọi alias không? **Không; phải xét ai còn sửa được tập được bọc.**
6. Vì sao không lưu ordinal? **Nó phụ thuộc vị trí khai báo, không phải mã cấu hình ổn định.**
7. allOf có luôn phù hợp làm mặc định không? **Không; hằng mới có thể tự được bật dù không có quyết định hành vi rõ ràng.**
