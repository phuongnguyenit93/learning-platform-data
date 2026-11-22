# Giữ hợp đồng public nhỏ và dễ tiến hóa

Một interface là ranh giới giữa điều một thành phần cam kết cung cấp và cách nó thực hiện điều đó. Hợp đồng public càng chứa nhiều chi tiết không cần thiết thì càng có nhiều thứ mà người dùng API có thể phụ thuộc vào, và càng khó thay đổi ở phiên bản sau.

Trong Java, phương thức có thân vẫn có thể là một phần của API. Phương thức `default` và `static` không tự động trở thành chi tiết nội bộ. Từ Java 9, interface có thể dùng phương thức `private` và `private static` để chia sẻ mã triển khai bên trong mà không mở rộng hợp đồng public.

## 1. Hợp đồng public gồm những gì?

Hợp đồng public (public contract) là tập hợp những điều mã bên ngoài được phép gọi, triển khai và dựa vào. Nó không chỉ là tên phương thức. Hợp đồng còn bao gồm:

- Tên, kiểu tham số, kiểu trả về, generic bounds và mức truy cập.
- Các ngoại lệ được khai báo và điều kiện có thể phát sinh ngoại lệ.
- Ý nghĩa của kết quả, quy tắc xử lý `null`, thứ tự xử lý và các trường hợp biên.
- Quyền sở hữu dữ liệu, khả năng thay đổi (mutability), tính an toàn luồng (thread safety) và vòng đời nếu những điều đó được cam kết.
- Những hành vi mà implementer phải cung cấp và những hành vi mà caller có thể gọi.

Một phương thức có thân không đồng nghĩa với phương thức nội bộ. Caller vẫn có thể phụ thuộc vào một phương thức `default` hoặc `static` public. Nếu đổi tên, xóa hoặc đổi ý nghĩa phương thức đó, thay đổi có thể ảnh hưởng đến người dùng API.

Mục tiêu của hợp đồng nhỏ là giữ lại các khả năng ổn định và cần thiết. “Nhỏ” không có nghĩa là cố giảm số phương thức bằng mọi giá; interface vẫn phải đủ rõ để caller hiểu và implementer có thể thực hiện đúng trách nhiệm.

## 2. Các loại phương thức trong interface

| Khai báo | Ai có thể gọi? | Vai trò |
|---|---|---|
| `String read();` | Caller gọi được; lớp triển khai phải cung cấp nếu chưa kế thừa được implementation phù hợp | Khả năng bắt buộc của hợp đồng |
| `default String readNormalized()` | Caller gọi được; lớp triển khai kế thừa hoặc override | Hành vi public dùng chung |
| `static TextSource of(...)` | Caller gọi qua tên interface | Factory hoặc thao tác public gắn với interface |
| `private String normalize(...)` | Chỉ mã bên trong chính interface | Helper instance nội bộ |
| `private static String requireText(...)` | Chỉ mã bên trong chính interface | Helper static nội bộ |

Các quy tắc cần nhớ:

- Phương thức interface không ghi access modifier mặc định là `public`. Phương thức thông thường không có thân là `public abstract`; phương thức `default` và `static` cũng là public nếu không khai báo `private`.
- Phương thức `default` được lớp triển khai kế thừa và có thể được override. Vì caller có thể gọi nó, đây là một phần của public API.
- Phương thức `static` của interface được gọi qua tên interface, ví dụ `TextSource.of(...)`. Phương thức static của interface không được kế thừa như phương thức instance của lớp triển khai hoặc subinterface.
- Phương thức `private` và `private static` không được kế thừa, không thể được override và không thể được gọi từ lớp triển khai hay caller bên ngoài interface.
- Field khai báo trong interface luôn là `public static final`. Vì vậy interface không phải nơi lưu trạng thái riêng cho từng instance; hằng số đặt ở đây cũng trở thành một phần của API.

### Phương thức private instance

Một phương thức private không có `static` chạy trong ngữ cảnh instance của đối tượng triển khai. Nó có thể dùng `this` và gọi các phương thức instance khác của interface, kể cả phương thức abstract do lớp triển khai cung cấp. Nó thường được gọi từ phương thức `default` hoặc từ phương thức private instance khác trong cùng interface.

Nó phải có thân phương thức. Lớp triển khai không phải viết implementation cho helper này và không thể gọi helper để tái sử dụng trực tiếp.

### Phương thức private static

Một phương thức private có `static` phù hợp với logic không cần trạng thái instance. Nó có thể được gọi từ phương thức static hoặc instance trong cùng interface.

Phương thức static không thể gọi helper private instance vì không có instance để gọi. Khi một đoạn kiểm tra hoặc chuyển đổi được dùng chung bởi factory static và phương thức default, helper private static thường là lựa chọn phù hợp.

Cả hai dạng private đều có từ Java 9. Chúng giúp gom logic lặp lại ngay tại nơi định nghĩa hợp đồng, nhưng không biến logic đó thành một điểm mở rộng public.

## 3. Ví dụ chạy được

Ví dụ sau giữ một phương thức trừu tượng làm khả năng bắt buộc. Hai phương thức default cung cấp hành vi tiện ích có thể suy ra từ khả năng đó. Hai helper private chia sẻ phần kiểm tra và chuẩn hóa dữ liệu mà không xuất hiện trong API.

```java
import java.util.Objects;

@FunctionalInterface
interface TextSource {
    String read();

    default String readNormalized() {
        return normalize(read());
    }

    default boolean isEmpty() {
        return readNormalized().isEmpty();
    }

    private String normalize(String value) {
        return requireText(value, "read()").strip();
    }

    static TextSource of(String value) {
        String checked = requireText(value, "value");
        return () -> checked;
    }

    private static String requireText(String value, String parameterName) {
        return Objects.requireNonNull(value, parameterName);
    }
}

public class Main {
    public static void main(String[] args) {
        TextSource source = TextSource.of("  Java interfaces  ");
        System.out.println(source.readNormalized());
        System.out.println(source.isEmpty());

        TextSource blank = TextSource.of("   ");
        System.out.println(blank.isEmpty());
    }
}
```

Lưu mã vào `Main.java`, sau đó chạy bằng JDK 17 trở lên:

```bash
javac Main.java
java Main
```

Kết quả stdout:

```text
Java interfaces
false
true
```

Giải thích:

1. `read()` là phương thức trừu tượng duy nhất. `@FunctionalInterface` xác nhận interface vẫn là functional interface dù có thêm các phương thức default, static và private.
2. `readNormalized()` và `isEmpty()` là phương thức public mà caller được phép sử dụng. Chúng tạo thành một phần của hợp đồng.
3. `normalize()` là helper private instance. Nó chỉ phục vụ logic bên trong interface và không tạo thêm yêu cầu cho lớp triển khai.
4. `of()` là factory static public. Caller gọi nó qua `TextSource.of(...)`; lớp triển khai không kế thừa factory này.
5. `requireText()` là helper private static. Factory static và helper instance đều dùng được nó mà không công khai chi tiết kiểm tra `null`.
6. `strip()` loại bỏ khoảng trắng Unicode ở hai đầu chuỗi. API này có từ Java 11; ví dụ được biên dịch và chạy bằng JDK 24. Riêng khả năng khai báo phương thức private trong interface cần Java 9 trở lên.

Trong ví dụ một tệp, `TextSource` được để ở mức package-private để cùng tồn tại với `public class Main`. Trong thư viện thực tế, nếu interface là API public, hãy đặt nó trong `TextSource.java` và khai báo `public interface TextSource`.

## 4. Quyết định điều gì nên public

Dùng phương thức public abstract khi implementer thực sự phải cung cấp một khả năng. Tên và hợp đồng của phương thức nên mô tả điều caller cần, không mô tả từng bước thuật toán nội bộ.

Dùng phương thức default khi hành vi:

- Có ý nghĩa với mọi implementation của interface.
- Có thể được tính từ các phương thức public ổn định đã có.
- Có quy tắc nhất quán về dữ liệu, ngoại lệ và kết quả.
- Đáng để caller sử dụng như một phần chính thức của API.

Dùng helper private khi đoạn mã chỉ là chi tiết triển khai được nhiều phương thức trong cùng interface dùng chung. Nếu chỉ muốn chia sẻ một đoạn kiểm tra hoặc chuyển đổi, không cần tạo thêm một phương thức default public.

Dùng phương thức static public khi caller thực sự cần một factory hoặc thao tác gắn với interface. Vì nó public, tên, tham số và hành vi của nó cũng cần được duy trì như API. Nếu chỉ là helper cho factory, hãy cân nhắc private static.

Nếu một khả năng chỉ có ở một nhóm implementation, hãy cân nhắc interface mở rộng riêng cho khả năng đó. Không nên thêm một phương thức bắt buộc vào interface cốt lõi chỉ để phục vụ một số implementation.

Nếu logic cần trạng thái mutable, constructor, dependency được inject hoặc nhiều hook mở rộng có kiểm soát, hãy cân nhắc đặt logic trong lớp triển khai, composition hoặc abstract class. Interface phù hợp để mô tả khả năng; helper private không biến interface thành nơi quản lý toàn bộ vòng đời đối tượng.

## 5. Tiến hóa interface mà không làm hợp đồng phình to

Một quy trình thiết kế thực tế:

1. Xác định caller cần làm được việc gì và implementer cần cam kết điều gì.
2. Giữ các phương thức abstract ở mức khả năng cốt lõi. Không đưa từng bước xử lý nội bộ thành một phương thức public.
3. Đặt hành vi dùng chung có thể suy ra từ hợp đồng vào default method khi hành vi đó đúng với mọi implementation.
4. Tách phần lặp lại giữa các default method thành helper private instance hoặc private static.
5. Đặt khả năng tùy chọn vào interface riêng nếu không phải mọi implementation đều cần hỗ trợ.
6. Ghi rõ quy tắc về `null`, ngoại lệ, mutability, thứ tự và thread safety. Đừng để caller phải suy đoán từ cách cài đặt hiện tại.
7. Viết test dựa trên hành vi public. Có thể thay đổi helper private trong tương lai, nhưng kết quả mà caller được cam kết phải tiếp tục đúng.

Không nên công khai một helper chỉ vì muốn tái sử dụng nó. Khi helper trở thành public, caller có thể bắt đầu gọi nó và implementer có thể override nó nếu đó là default method. Khi ấy, một chi tiết vốn có thể đổi tự do đã trở thành trách nhiệm duy trì lâu dài.

Cũng không nên dùng private để che giấu một khả năng mà caller thực sự cần hoặc implementer thực sự phải cung cấp. Nếu một thao tác là phần cốt lõi của abstraction, nó phải được mô tả công khai và có hợp đồng rõ ràng.

## 6. Tác động tương thích khi thay đổi interface

| Thay đổi | Tác động cần xem xét |
|---|---|
| Thêm phương thức abstract | Các implementation cụ thể hiện có thường phải bổ sung phương thức khi biên dịch lại. Binary cũ có thể gặp `AbstractMethodError` nếu lời gọi mới đi tới implementation chưa có phương thức đó. |
| Thêm phương thức default | Nhiều implementation hiện có có thể kế thừa hành vi mới mà không phải viết thêm mã. Tuy nhiên, phương thức có thể xung đột với default method từ interface khác hoặc với cấu trúc kế thừa hiện tại. |
| Thêm hoặc refactor helper private | Không tạo phương thức caller có thể gọi và không tạo nghĩa vụ implementation mới. Tuy vậy, nếu helper được default method sử dụng, đổi logic helper vẫn có thể đổi hành vi quan sát được. |
| Đổi chữ ký hoặc ngữ nghĩa public | Thay đổi tham số, kiểu trả về, generic bounds, checked exceptions hoặc ý nghĩa kết quả có thể phá source compatibility, binary compatibility hoặc behavioral compatibility. |

Khi nhiều nguồn cung cấp default method cùng chữ ký, quy tắc lựa chọn cần được hiểu rõ:

- Phương thức instance phù hợp từ superclass được ưu tiên hơn default method của interface.
- Nếu một interface cụ thể hơn kế thừa interface khác và cùng cung cấp default method, implementation từ interface cụ thể hơn được ưu tiên.
- Nếu hai interface không có quan hệ kế thừa cung cấp default method xung đột, lớp triển khai phải override và tự chọn hành vi.

Do đó, thêm default method thường ít gây áp lực hơn thêm abstract method, nhưng không phải lúc nào cũng an toàn. Trước khi thêm, hãy kiểm tra các interface mà lớp triển khai có thể kết hợp, các phương thức đã tồn tại trong lớp cha và ý nghĩa của hành vi mới đối với caller.

## 7. Lỗi thiết kế thường gặp

- **Dùng default method chỉ để làm helper:** helper trở thành public API. Hãy dùng private method nếu caller không cần gọi nó.
- **Coi mọi default method là chi tiết nội bộ:** caller gọi được và có thể phụ thuộc vào hành vi của nó. Hãy duy trì nó như một phần hợp đồng.
- **Thêm abstract method cho một nhu cầu riêng lẻ:** mọi implementation cụ thể có thể phải thay đổi. Hãy cân nhắc interface mở rộng.
- **Để helper private chứa nghiệp vụ cần dependency hoặc state:** chuyển phần đó vào implementation class hoặc composition để trách nhiệm rõ ràng.
- **Gọi helper instance từ phương thức static:** không hợp lệ vì static context không có instance. Dùng helper private static nếu logic không cần trạng thái instance.
- **Đặt trạng thái mutable vào interface:** field interface luôn là public static final và không phải state riêng của object.
- **Cho rằng thêm default method luôn tương thích:** vẫn phải kiểm tra xung đột, phương thức đã tồn tại và thay đổi hành vi.
- **Ẩn một khả năng bắt buộc bằng private:** implementer và caller không thể dùng nó như hợp đồng. Khả năng cốt lõi phải được khai báo public.

## 8. Checklist trước khi công bố API

- Phương thức này có phải khả năng mà caller cần gọi hoặc implementer phải cung cấp không?
- Nếu không, nó có thể là helper private trong interface không?
- Default method có thể được suy ra đúng từ hợp đồng hiện tại cho mọi implementation không?
- Phương thức mới có làm xuất hiện xung đột với interface hoặc superclass khác không?
- Quy tắc về `null`, ngoại lệ, mutability và thread safety đã rõ chưa?
- Interface có đang phơi bày kiểu triển khai, cấu trúc dữ liệu hoặc thuật toán mà caller không cần biết không?
- Test đã bao phủ hành vi public và các implementation đại diện chưa?

Một hợp đồng public tốt chỉ cam kết những khả năng thực sự cần thiết, mô tả rõ hành vi và để phần triển khai có không gian thay đổi. Phương thức private trong interface từ Java 9 là công cụ hữu ích để giữ ranh giới đó: chia sẻ mã bên trong mà không biến helper thành nghĩa vụ hoặc điểm phụ thuộc mới của người dùng API.
