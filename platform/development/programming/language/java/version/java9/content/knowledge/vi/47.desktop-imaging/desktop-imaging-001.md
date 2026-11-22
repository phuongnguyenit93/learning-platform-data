# Ảnh nhiều độ phân giải qua MultiResolutionImage trong Java

## 1. Mục tiêu

Khi hiển thị giao diện AWT/Swing trên màn hình HiDPI, một icon chỉ có ảnh raster 24×24 pixel có thể bị phóng lên để phục vụ màn hình 150% hoặc 200% và trở nên nhòe. Ngược lại, dùng trực tiếp file 48×48 như một icon “48 đơn vị giao diện” sẽ làm icon to gấp đôi mức mong muốn. `java.awt.image.MultiResolutionImage` giải quyết bằng cách **gom nhiều ảnh raster của cùng một hình ở các độ phân giải khác nhau thành một ảnh logic**, để hệ thống vẽ có thể chọn ảnh phù hợp.

Sau bài này, bạn có thể:

- Phân biệt **kích thước logic** (logical/user-space size), **độ phân giải pixel của ảnh nguồn** và **pixel thiết bị** trên màn hình HiDPI.
- Dùng `MultiResolutionImage`, `BaseMultiResolutionImage` và `AbstractMultiResolutionImage` đúng vai trò.
- Giải thích khi nào `getResolutionVariant(width, height)` trả ảnh 1×, 2×, 3× hoặc ảnh lớn nhất sẵn có.
- Vẽ một ảnh logic bằng `Graphics2D.drawImage`, hiểu quy tắc chọn resolution variant và các `RenderingHints` liên quan.
- Nạp asset raster cho Swing theo cách rõ ràng và kiểm thử độc lập với việc có màn hình thật hay không.
- Nhận biết lỗi phổ biến liên quan tỷ lệ, thứ tự ảnh, chất lượng raster, bộ nhớ và môi trường nhiều màn hình.

**Phiên bản Java:** `MultiResolutionImage`, `AbstractMultiResolutionImage` và `BaseMultiResolutionImage` là API công khai của module `java.desktop` từ Java 9 và tiếp tục có trong Java hiện đại. Ví dụ chạy được với JDK 17+; không dùng API nội bộ, không dựa vào cơ chế từng chỉ có ở các bản Java cũ. API này phục vụ **Java AWT/Swing và xử lý hình ảnh Java2D**, không phải trình duyệt web.

## 2. Một ảnh logic, nhiều raster

Giả sử ứng dụng muốn icon có kích thước logic **24×24**:

| Asset | Kích thước pixel trong file | Mục đích |
| --- | --- | --- |
| `save.png` (1×) | 24×24 | Bản cơ sở, thích hợp yêu cầu khoảng 24×24 pixel đích |
| `save@2x.png` (2×) | 48×48 | Giữ chi tiết khi vùng vẽ cần khoảng 48×48 pixel |
| `save@3x.png` (3×) | 72×72 | Phục vụ mức phóng đại lớn hơn |

Ví dụ cách quy đổi thường gặp khi một icon có bề rộng 24 đơn vị user-space:

```text
Kích thước giao diện: 24 × 24 đơn vị (logical/user space)
                 |
                 +-- scale 1.00 -> khoảng 24 × 24 pixel thiết bị -> ảnh 1×
                 |
                 +-- scale 1.50 -> khoảng 36 × 36 pixel thiết bị -> ảnh 2× có thể phù hợp
                 |
                 +-- scale 2.00 -> khoảng 48 × 48 pixel thiết bị -> ảnh 2×
                 |
                 +-- scale 2.50 -> khoảng 60 × 60 pixel thiết bị -> ảnh 3×
```

Đây là mô hình trực quan. Trên màn hình thật, cách Java2D chọn ảnh còn tùy phép biến đổi của `Graphics2D`, loại lệnh `drawImage`, rendering hint, DPI và implementation. Không mặc định mọi màn hình 150% đều buộc phải chọn ảnh 2× bằng mọi renderer. Dùng thử nghiệm trên chính hệ điều hành, JDK và thiết bị cần hỗ trợ.

**Điều cốt lõi:** HiDPI không làm đổi thiết kế icon từ 24 đơn vị thành 48 đơn vị. Nó làm tăng số **pixel vật lý** dùng để hiển thị cùng một đối tượng logic. Asset 2× có thêm chi tiết để tái tạo hình sắc nét ở số pixel lớn hơn.

Ảnh 2× phải là một raster được thiết kế hoặc xuất lại ở độ phân giải 2× từ nguồn có đủ chi tiết. Nếu chỉ phóng ảnh 24×24 lên 48×48 bằng nội suy, chất lượng chi tiết vốn đã thiếu sẽ không tự phục hồi.

## 3. Các API liên quan

### 3.1. `MultiResolutionImage` — hợp đồng lựa chọn độ phân giải

`MultiResolutionImage` là interface thuộc `java.awt.image`, gồm hai phương thức:

```java
Image getResolutionVariant(double destImageWidth, double destImageHeight);
List<Image> getResolutionVariants();
```

Đây là **chữ ký API minh họa**, không phải chương trình Java độc lập.

- `getResolutionVariant(w, h)` nhận **kích thước pixel mong muốn tại đích**, rồi trả về một `Image` đủ phù hợp theo chính sách của implementation. Hai tham số có kiểu `double` để hỗ trợ kích thước tỷ lệ không nguyên.
- `getResolutionVariants()` trả danh sách các raster đã có. Danh sách phải có ít nhất một ảnh, và nhiều implementation trả danh sách **không cho phép chỉnh sửa**.
- `w` và `h` phải hữu hạn và **lớn hơn 0**. Giá trị 0, âm, `NaN` hoặc vô cực phải được từ chối bằng `IllegalArgumentException` theo hợp đồng interface.

**Một chi tiết quan trọng về kiểu dữ liệu:** `MultiResolutionImage` là interface **không tự kế thừa** `java.awt.Image`. Một đối tượng dùng được với `Graphics.drawImage(Image, ...)` phải đồng thời là một `Image`; các lớp có sẵn `BaseMultiResolutionImage` và `AbstractMultiResolutionImage` đều kế thừa `Image` và triển khai interface.

```java
BaseMultiResolutionImage image = new BaseMultiResolutionImage(oneX, twoX);
MultiResolutionImage variants = image; // Truy cập hợp đồng variants
graphics.drawImage(image, 0, 0, 24, 24, null); // Truyền kiểu Image
```

Đây là đoạn minh họa giả sử `oneX`/`twoX` là ảnh đã tải và `graphics` là `Graphics2D` hợp lệ.

### 3.2. `BaseMultiResolutionImage` — dùng cho bộ ảnh raster có sẵn

`BaseMultiResolutionImage` là implementation đã có sẵn, dựa trên một mảng `Image`. Đối với phần lớn trường hợp một icon có 1×/2×/3×, bạn chỉ cần:

```java
Image icon = new BaseMultiResolutionImage(image1x, image2x, image3x);
```

Ảnh phải không null, mảng phải có ít nhất một phần tử và nên sắp tăng dần về **cả chiều rộng lẫn chiều cao**. Theo thuật toán của `BaseMultiResolutionImage`:

1. Đi theo thứ tự ảnh trong mảng.
2. Trả ảnh **đầu tiên** có **width >= destImageWidth** **và height >= destImageHeight**.
3. Nếu không ảnh nào đủ cả hai chiều, trả **ảnh cuối cùng**.

Ví dụ với [24×24, 48×48, 72×72]:

| Gọi thủ công | Ảnh được chọn | Lý do |
| --- | --- | --- |
| `getResolutionVariant(24, 24)` | 24×24 | Ảnh đầu đủ hai chiều |
| `getResolutionVariant(36, 36)` | 48×48 | 24 nhỏ hơn yêu cầu; 48 đủ |
| `getResolutionVariant(48, 48)` | 48×48 | Vừa đủ |
| `getResolutionVariant(60, 60)` | 72×72 | Ảnh 3× là bản đầu đủ |
| `getResolutionVariant(90, 90)` | 72×72 | Không có ảnh đủ lớn; lấy ảnh cuối |

Trong trường hợp cần chỉ định **ảnh cơ sở** không phải phần tử đầu, lớp còn cung cấp constructor với `baseImageIndex`. `getWidth(null)` và `getHeight(null)` của đối tượng `BaseMultiResolutionImage` tương ứng ảnh cơ sở, không phải kích thước của biến thể lớn nhất. Với constructor nhận `Image...` trong ví dụ, ảnh cơ sở là phần tử đầu.

Đừng dựa vào quy tắc “chọn gần nhất” theo khoảng cách tuyệt đối; `BaseMultiResolutionImage` chọn ảnh đầu tiên **không nhỏ hơn kích thước yêu cầu ở cả hai chiều**, sau đó fallback ảnh cuối.

### 3.3. `AbstractMultiResolutionImage` — khi cần chính sách riêng

`AbstractMultiResolutionImage` cung cấp các cài đặt mặc định cho nhiều phương thức `Image`, ủy quyền kích thước và các thông tin liên quan cho `getBaseImage()`. Chỉ cần tự mở rộng lớp này nếu bộ ảnh đòi hỏi quy tắc chọn đặc biệt, lazy loading hoặc sinh biến thể theo yêu cầu. Khi đó lớp con cung cấp:

- `protected Image getBaseImage()`;
- `Image getResolutionVariant(double w, double h)`;
- `List<Image> getResolutionVariants()`.

Không cần tự triển khai lớp con nếu một danh sách raster sắp tăng dần đã giải quyết được yêu cầu: `BaseMultiResolutionImage` đơn giản hơn và dễ kiểm chứng hơn.

## 4. Vòng đời tài nguyên và cách nạp ảnh

### 4.1. `ImageIO.read` đọc từng raster, không tự tạo bộ variants

`ImageIO.read(...)` thường trả về một `BufferedImage` duy nhất ứng với dữ liệu đã đọc; nó không tự hiểu rằng hai file khác tên đại diện cho các biến thể cùng icon. Khi dùng asset 1×/2×, hãy nạp **hai file** rồi tạo một `BaseMultiResolutionImage`.

Ví dụ logic tải từ classpath, giả sử đã có tài nguyên:

- `src/main/resources/icons/save.png` — 24×24;
- `src/main/resources/icons/save@2x.png` — 48×48.

```java
URL lowUrl = Objects.requireNonNull(
        MyWindow.class.getResource("/icons/save.png"));
URL highUrl = Objects.requireNonNull(
        MyWindow.class.getResource("/icons/save@2x.png"));

BufferedImage low = ImageIO.read(lowUrl);
BufferedImage high = ImageIO.read(highUrl);
if (low == null || high == null) {
    throw new IOException("Unsupported or corrupt image resource");
}

Image multi = new BaseMultiResolutionImage(low, high);
JLabel label = new JLabel(new ImageIcon(multi));
```

**Đây là đoạn minh họa tích hợp**, không phải chương trình độc lập: `MyWindow` là lớp ứng dụng của bạn, cần import `java.net.URL`, `java.util.Objects`, `java.awt.Image`, `java.awt.image.BufferedImage`, `java.awt.image.BaseMultiResolutionImage`, `javax.imageio.ImageIO`, `javax.swing.ImageIcon`, `javax.swing.JLabel`, `java.io.IOException`. Phải có hai file resource thực tế. Nên nạp/giải mã ảnh khỏi Event Dispatch Thread khi I/O có thể chậm, sau đó tạo/cập nhật thành phần Swing trên EDT.

`ImageIcon` sử dụng kích thước cơ sở của `Image` cho bố cục. Khi Swing/Java2D vẽ, cơ chế chọn variant có thể cung cấp raster phù hợp với thiết bị, trong khi icon vẫn có kích thước logic dự kiến.

### 4.2. Tránh phụ thuộc vào quy ước tìm file theo nền tảng

Một số nền tảng/toolkit có thể tự nhận biết quy ước đặt tên cho ảnh nhiều độ phân giải khi nạp qua `Toolkit.getImage(...)`. **Không coi quy tắc này là bảo đảm đồng nhất giữa mọi hệ điều hành/runtime**. Nếu ứng dụng cần hành vi dễ tái lập và kiểm thử, tự tải danh sách file rồi tạo `BaseMultiResolutionImage` rõ ràng.

### 4.3. Chuẩn bị asset đúng cách

- Dùng **cùng bố cục và chủ thể**, cùng vùng trong suốt, cùng tỉ lệ nội dung giữa 1×/2×/3×. Nếu 2× có padding khác 1×, icon có thể “nhảy” khi chuyển màn hình.
- Cần phiên bản raster độ phân giải cao thực sự; không tạo bản 2× bằng cách phóng từ 1× rồi kỳ vọng nét hơn.
- Với icon trong suốt, dùng loại ảnh hỗ trợ alpha, ví dụ PNG giải mã thành `BufferedImage` có alpha.
- Xem xét bộ nhớ: 1 ảnh 24×24 RGBA khoảng 2.304 byte pixel; 48×48 khoảng 9.216 byte; 72×72 khoảng 20.736 byte, **chưa tính overhead và định dạng lưu trong JVM**. Nhiều icon/lần nạp lặp có thể tăng bộ nhớ đáng kể.
- Khi cùng asset được dùng nhiều lần, cân nhắc cache theo định danh resource, nhưng có chính sách giải phóng/cache phù hợp khi tài nguyên thay đổi.
- Nếu các ảnh có tỷ lệ khung hình khác nhau, việc chọn một biến thể “đủ kích thước” vẫn có thể gây méo, crop hoặc khác căn lề ở bước vẽ. Nên thiết kế các phiên bản cùng tỉ lệ.

## 5. Chương trình Java 17+ chạy độc lập, không cần màn hình

Ví dụ sau tự tạo ba `BufferedImage` màu khác nhau để nhìn thấy rõ variant được chọn. Màu **đỏ** đại diện 1×, **xanh dương** đại diện 2×, **xanh lá** đại diện 3×. Chương trình kiểm tra thuật toán chọn biến thể bằng API công khai, sau đó tạo `Graphics2D` trong bộ nhớ và mô phỏng scale 2×.

Lưu nguyên chương trình thành tệp **`MultiResolutionDemo.java`**:

```java
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.Image;
import java.awt.RenderingHints;
import java.awt.image.BaseMultiResolutionImage;
import java.awt.image.BufferedImage;
import java.awt.image.MultiResolutionImage;

public class MultiResolutionDemo {
    public static void main(String[] args) {
        BufferedImage one = square(24, Color.RED);
        BufferedImage two = square(48, Color.BLUE);
        BufferedImage three = square(72, Color.GREEN);
        BaseMultiResolutionImage image =
                new BaseMultiResolutionImage(one, two, three);
        MultiResolutionImage variants = image;

        System.out.printf("Base: %dx%d%n",
                image.getWidth(null), image.getHeight(null));
        System.out.println("Variant count: " +
                variants.getResolutionVariants().size());

        printChoice(variants, 24, 24);
        printChoice(variants, 36, 36);
        printChoice(variants, 48, 48);
        printChoice(variants, 60, 60);
        printChoice(variants, 90, 90);

        BufferedImage canvas =
                new BufferedImage(48, 48, BufferedImage.TYPE_INT_ARGB);
        Graphics2D graphics = canvas.createGraphics();
        try {
            graphics.setRenderingHint(
                    RenderingHints.KEY_RESOLUTION_VARIANT,
                    RenderingHints.VALUE_RESOLUTION_VARIANT_SIZE_FIT);
            graphics.scale(2.0, 2.0);
            graphics.drawImage(image, 0, 0, 24, 24, null);
        } finally {
            graphics.dispose();
        }

        int pixel = canvas.getRGB(24, 24);
        System.out.println("Rendered at 2x: " +
                (pixel == Color.BLUE.getRGB() ? "BLUE" : "OTHER"));
    }

    static BufferedImage square(int side, Color color) {
        BufferedImage result =
                new BufferedImage(side, side, BufferedImage.TYPE_INT_ARGB);
        Graphics2D graphics = result.createGraphics();
        try {
            graphics.setColor(color);
            graphics.fillRect(0, 0, side, side);
        } finally {
            graphics.dispose();
        }
        return result;
    }

    static void printChoice(MultiResolutionImage image, int width, int height) {
        Image chosen = image.getResolutionVariant(width, height);
        System.out.printf("Request %dx%d -> %dx%d%n", width, height,
                chosen.getWidth(null), chosen.getHeight(null));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 MultiResolutionDemo.java
java -Djava.awt.headless=true MultiResolutionDemo
```

**Kết quả tham chiếu** đã kiểm tra với OpenJDK 24, Java2D raster trên `BufferedImage`:

```text
Base: 24x24
Variant count: 3
Request 24x24 -> 24x24
Request 36x36 -> 48x48
Request 48x48 -> 48x48
Request 60x60 -> 72x72
Request 90x90 -> 72x72
Rendered at 2x: BLUE
```

Năm dòng `Request` là hành vi xác định của `BaseMultiResolutionImage` với ba ảnh được xây dựng trong ví dụ. Dòng `Rendered at 2x` thể hiện kết quả Java2D trong môi trường đã kiểm tra; **rendering hint là một gợi ý**, nên chính sách vẽ trên implementation khác có thể cho `OTHER`. Hãy kiểm tra lựa chọn tự động trên các nền tảng sản phẩm hỗ trợ.

**Giải thích chương trình:**

1. `square(...)` tạo `BufferedImage` ARGB 24/48/72 pixel, tô toàn bộ bằng một màu riêng và đóng `Graphics2D` bằng `dispose()`.
2. `BaseMultiResolutionImage(one, two, three)` tạo ảnh logic. `getWidth(null)` trả 24, là kích thước bản cơ sở.
3. `printChoice(...)` gọi trực tiếp `getResolutionVariant` và in kích thước raster được trả về. Nó **không vẽ**, nên không phụ thuộc DPI màn hình.
4. `canvas` có kích thước raster thực 48×48; `graphics.scale(2, 2)` biến vùng vẽ **24×24 user-space** thành **48×48 pixel đích**.
5. `KEY_RESOLUTION_VARIANT = VALUE_RESOLUTION_VARIANT_SIZE_FIT` gợi ý chọn variant dựa trên DPI và phép biến đổi vẽ. Khi implementation tuân theo gợi ý này, pixel giữa canvas có màu xanh dương từ bản 2×.
6. Chương trình không cần `JFrame` hoặc màn hình thật; thích hợp làm ví dụ đầu tiên và làm kiểm thử tính năng cơ bản trong CI.

**Không sao chép `graphics.scale(2, 2)` vào `paintComponent` của Swing như một “sửa lỗi HiDPI” mặc định.** Khi vẽ lên cửa sổ thật, `Graphics2D` đã có transform phụ thuộc thiết bị và chính sách Java2D. Tự scale thêm có thể khiến icon bị phóng đại hai lần. Trong chương trình này, scale chỉ mô phỏng màn hình 2× trên một ảnh `BufferedImage` offscreen có transform mặc định là identity.

## 6. Quy trình chọn variant khi vẽ

Khi bạn truyền một đối tượng `Image` cũng triển khai `MultiResolutionImage` cho `Graphics.drawImage(...)`, Java2D có thể hỏi implementation xem ảnh raster nào phù hợp để vẽ. Đường đi khái quát:

```text
Graphics2D.drawImage(multiImage, logicalRect)
                        |
                        v
           Xét transform + DPI + rendering hint
                        |
                        v
           Xác định kích thước pixel mong muốn
                        |
                        v
     MultiResolutionImage.getResolutionVariant(w, h)
                        |
                        v
           Chọn và scale variant vào logicalRect
```

Trong thực tế, raster được chọn phải được vẽ vào **hình chữ nhật đích logic** do ứng dụng yêu cầu. Đừng vì ảnh nguồn đang là 48×48 mà thay đổi bố cục `JLabel` thành 48×48 logical pixels nếu yêu cầu giao diện là 24×24.

### RenderingHints liên quan

`RenderingHints.KEY_RESOLUTION_VARIANT` hỗ trợ các giá trị sau (từ Java 9):

| Giá trị | Ý nghĩa |
| --- | --- |
| `VALUE_RESOLUTION_VARIANT_DEFAULT` | Implementation chọn heuristic mặc định, có thể phụ thuộc nền tảng |
| `VALUE_RESOLUTION_VARIANT_BASE` | Yêu cầu dùng ảnh có độ phân giải cơ sở |
| `VALUE_RESOLUTION_VARIANT_DPI_FIT` | Chọn dựa trên DPI của màn hình |
| `VALUE_RESOLUTION_VARIANT_SIZE_FIT` | Chọn dựa trên DPI và transform của `Graphics2D` |

Đây là các **hints**, không phải hợp đồng bắt buộc mọi renderer đều hỗ trợ và xử lý như nhau. `RenderingHints.KEY_INTERPOLATION` (ví dụ bilinear/bicubic) là vấn đề **nội suy pixel sau khi chọn raster**, khác với việc **chọn raster nào**. Một hint nội suy tốt không thể phục hồi chi tiết không có trong ảnh nguồn 1×.

Một điểm thường gây nhầm lẫn: `getResolutionVariant(36, 36)` là lời gọi **trực tiếp**, có kết quả theo thuật toán của `BaseMultiResolutionImage`. Còn `drawImage(...)` tự quyết định cần hỏi kích thước nào theo context, rồi có thể dùng ảnh khác nhau giữa những môi trường vẽ. Không nên viết test cứng rằng mọi phương thức `drawImage` ở mọi hệ điều hành chắc chắn gọi `getResolutionVariant(36, 36)`.

## 7. Sử dụng đúng trong Swing

Với Swing, một cách triển khai thường gặp là:

1. Nạp assets cho mỗi độ phân giải từ tài nguyên của ứng dụng.
2. Tạo `BaseMultiResolutionImage` một lần cho từng bộ icon.
3. Truyền `Image` đó vào `new ImageIcon(image)` hoặc vẽ bằng `Graphics.drawImage(image, ...)` khi thiết kế một component riêng.
4. Giữ **kích thước logic nhất quán**; Java2D chọn variant phù hợp khi có thể.
5. Cập nhật cây thành phần Swing trên **Event Dispatch Thread (EDT)**; tránh I/O nặng trong `paintComponent`.

Đoạn minh họa tích hợp sau giả sử biến `image` đã là `BaseMultiResolutionImage` được tạo từ các asset 24×24 và 48×48:

```java
SwingUtilities.invokeLater(() -> {
    JFrame frame = new JFrame("HiDPI icon");
    JLabel label = new JLabel("Save", new ImageIcon(image), JLabel.LEADING);
    frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
    frame.add(label);
    frame.pack();
    frame.setLocationRelativeTo(null);
    frame.setVisible(true);
});
```

Cần import `javax.swing.SwingUtilities`, `javax.swing.JFrame`, `javax.swing.JLabel` và `javax.swing.ImageIcon`; đây **không** phải chương trình độc lập vì `image` được chuẩn bị ở bên ngoài. Với ứng dụng thực tế, nạp ảnh trước rồi hiển thị trên EDT. Nếu icon nằm trong nhiều cửa sổ, cân nhắc dùng chung đối tượng ảnh đã nạp, nhưng không chỉnh sửa nội dung `BufferedImage` sau khi công bố cho các component.

### Trên hệ thống nhiều màn hình

Tỷ lệ scale có thể khác nhau giữa màn hình, thậm chí là 125%, 150%, 200% và khác theo cấu hình hệ điều hành. Không cache duy nhất một variant đã chọn bằng tay dựa trên DPI của màn hình đầu tiên rồi dùng mãi khi cửa sổ được kéo sang màn hình khác. Hãy giữ đối tượng `MultiResolutionImage` logic để Java2D có cơ hội chọn lại khi vẽ.

Nếu cần chẩn đoán, `GraphicsConfiguration.getDefaultTransform()` cung cấp transform mặc định phù hợp với cấu hình đồ họa đang xét, nhưng không phải mọi phép vẽ đều chỉ chịu tác động của transform đó; `Graphics2D.getTransform()` còn chứa các phép biến đổi ứng dụng. Đoạn test headless ở `BufferedImage` không chứng minh toàn bộ hành vi của cửa sổ trên hệ điều hành, vì nó không có cấu hình màn hình thật.

## 8. Tự kiểm thử tính chọn biến thể với JUnit 5

Kiểm thử **API chọn ảnh thủ công** có tính xác định và chạy được trong chế độ headless. Đây là ví dụ JUnit Jupiter; cần thư viện JUnit 5 trong test runtime, **không** phải lớp có `main` độc lập:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.awt.Image;
import java.awt.image.BaseMultiResolutionImage;
import java.awt.image.BufferedImage;
import java.awt.image.MultiResolutionImage;
import org.junit.jupiter.api.Test;

class MultiResolutionImageTest {
    @Test
    void selectsFirstVariantLargeEnoughInBothDimensions() {
        BufferedImage small = new BufferedImage(
                24, 24, BufferedImage.TYPE_INT_ARGB);
        BufferedImage medium = new BufferedImage(
                48, 48, BufferedImage.TYPE_INT_ARGB);
        BufferedImage large = new BufferedImage(
                72, 72, BufferedImage.TYPE_INT_ARGB);

        MultiResolutionImage image =
                new BaseMultiResolutionImage(small, medium, large);

        assertSame(small, image.getResolutionVariant(24, 24));
        assertSame(medium, image.getResolutionVariant(36, 36));
        assertSame(large, image.getResolutionVariant(60, 60));
        assertSame(large, image.getResolutionVariant(90, 90));
        assertEquals(3, image.getResolutionVariants().size());
    }

    @Test
    void rejectsInvalidDestinationSize() {
        Image small = new BufferedImage(
                24, 24, BufferedImage.TYPE_INT_ARGB);
        MultiResolutionImage image = new BaseMultiResolutionImage(small);

        assertThrows(IllegalArgumentException.class,
                () -> image.getResolutionVariant(0, 24));
        assertThrows(IllegalArgumentException.class,
                () -> image.getResolutionVariant(Double.NaN, 24));
    }
}
```

Test đầu kiểm tra trực tiếp quy tắc “ảnh đầu tiên đủ lớn ở **cả hai chiều**”. Test sau đảm bảo đối số kích thước bất hợp lệ bị từ chối theo hợp đồng API. Không cần có thiết bị HiDPI thật để chạy các test này.

Với **test render thực sự** ở nhiều DPI, nên bổ sung test tích hợp/screenshot trên các môi trường mục tiêu, vì `RenderingHints` có thể được implementation xử lý khác nhau. Không xác định thành công chỉ bằng việc `getResolutionVariants().size() == 3`; một bộ ba ảnh có nội dung/căn lề sai vẫn có thể khiến UI bị nhòe hoặc giật.

## 9. Bộ tiêu chí kiểm thử thực tế

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| 100% / 1× | Icon được bố trí đúng **24×24 logical**, không bị phóng thành 48×48 |
| 125% / 1,25× | Hình có nét phù hợp; trường hợp chọn 2× rồi thu nhỏ có thể chấp nhận theo thiết kế |
| 150% / 1,5× | Các cạnh và chi tiết sắc hơn khi dùng raster đủ độ phân giải |
| 200% / 2× | Raster 48×48 được cung cấp và vẽ vào khu vực 24×24 logical |
| 250% hoặc lớn hơn | Có 3× hoặc fallback ảnh lớn nhất; không hứa không bị mờ khi thiếu độ phân giải |
| Chuyển cửa sổ giữa các màn hình có scale khác nhau | Bố cục logic ổn định; variant được xem xét lại khi render |
| Resize icon từ 24 lên 32 logical | Kiểm tra kích thước pixel đích tương ứng và quy tắc chọn variant |
| Trong suốt, viền, padding, font bên trong icon | Nội dung của 1×/2×/3× được căn chỉnh như nhau |
| File resource thiếu/hỏng | Nạp ảnh báo lỗi rõ ràng, không trả ảnh null vào mảng variants |
| Số lượng icon lớn | Không tải trùng tài nguyên không cần thiết; dùng chính sách cache hợp lý |
| Chạy CI headless | Test chọn variant thủ công chạy được, không đòi màn hình hoặc `JFrame` |

Nên kiểm tra ít nhất một hệ Windows và một hệ Linux/macOS nếu đó là nền tảng sản phẩm yêu cầu; cách quản lý scale do hệ điều hành, desktop environment, JDK và thiết bị quyết định. Các test screenshot nên ghi lại phiên bản JDK, hệ điều hành, DPI và scale để có thể tái lập.

## 10. Lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Icon trên màn hình 2× vẫn nhòe | Chỉ có raster 1×, hoặc raster 2× chỉ là ảnh 1× phóng to | Thiết kế/xuất bản 2× thực sự từ nguồn đủ chi tiết |
| Icon hiển thị to gấp đôi | Dùng kích thước pixel 2× làm kích thước layout logic | Giữ layout 24×24, để pipeline chọn raster thích hợp |
| `getResolutionVariant(36,36)` trả 72×72 dù có ảnh 48×48 | Mảng ảnh không sắp theo độ phân giải tăng dần | Sắp lại ảnh để mỗi bản sau đủ lớn ở cả hai chiều |
| Trên màn hình 150% icon có padding khác | Các asset 1×/2× không căn nội dung giống nhau | Chuẩn hóa bố cục và vùng trong suốt khi xuất asset |
| Nghĩ `MultiResolutionImage` có thể truyền trực tiếp cho mọi API nhận `Image` | Interface không kế thừa `Image` | Dùng kiểu cụ thể `BaseMultiResolutionImage` hoặc tham chiếu `Image` cho `drawImage` |
| Dùng `ImageIO.read("save@2x.png")` và nghĩ Java tự biết bản 1× | `ImageIO` trả một `BufferedImage` đơn lẻ | Nạp cả hai raster rồi tạo `BaseMultiResolutionImage` |
| Test vẽ offscreen khác screenshot trên màn hình | Render hint, DPI/transform và graphics pipeline khác nhau | Phân biệt unit test `getResolutionVariant` với integration test GUI |
| Sử dụng ảnh 2× sau khi chọn thủ công rồi quên scale về đích | Đang vẽ ảnh nguồn theo kích thước pixel của nó | Vẽ vào hình chữ nhật logical đúng kích thước thiết kế |
| Icon hiển thị sai sau khi chuyển màn hình | Cache biến thể đã chọn trước đó theo DPI đầu tiên | Giữ đối tượng multi-resolution, cho renderer chọn lại |
| Ảnh nặng hoặc giật khung hình | Giải mã file trong `paintComponent` hoặc tạo variants liên tục | Nạp/tạo/cache hợp lý trước khi vẽ, tránh I/O trên EDT |
| Tốn bộ nhớ không cần thiết | Giữ mọi asset lớn và nhiều bản sao không sử dụng | Chọn tập resolution phù hợp và quản lý vòng đời/cache |

Một nhầm lẫn nữa: `RenderingHints.KEY_INTERPOLATION` điều khiển phương pháp nội suy trong quá trình scale; nó **không tạo** dữ liệu chi tiết 2×. Tương tự, đổi `Graphics2D.scale(...)` không tự tạo ảnh raster chất lượng cao. Bạn cần các variant thực sự trong tài nguyên.

## 11. Checklist triển khai

- [ ] Xác định kích thước **logical** mong muốn cho từng icon/component.
- [ ] Chuẩn bị asset 1×, 2× (và 3× khi cần), cùng nội dung, tỉ lệ và vùng trong suốt.
- [ ] Nạp file thành các `Image` không null, kiểm tra kích thước thực và thứ tự ảnh.
- [ ] Tạo `BaseMultiResolutionImage` với các variant theo thứ tự tăng ở cả hai chiều.
- [ ] Truyền ảnh logic vào Java2D/Swing; không thay đổi layout theo số pixel nguồn 2×.
- [ ] Không chia sẻ một biến thể đã chọn sẵn cho mọi DPI nếu cửa sổ có thể chuyển màn hình.
- [ ] Có test headless cho `getResolutionVariant`, danh sách variants và đối số không hợp lệ.
- [ ] Có kiểm thử GUI thực trên các tỷ lệ scale/hệ điều hành mà sản phẩm hỗ trợ.
- [ ] Tải và cache tài nguyên hợp lý, không I/O/block trong `paintComponent` hay EDT.
- [ ] Không phụ thuộc quy ước tự tìm `@2x` của toolkit nếu sản phẩm cần hành vi thống nhất trên mọi nền tảng.

## 12. Câu hỏi ôn tập

1. Vì sao ảnh 48×48 không đồng nghĩa icon phải chiếm 48×48 đơn vị bố cục?
2. Với ba raster 24/48/72, `getResolutionVariant(36,36)` trả raster nào? Vì sao?
3. Nếu yêu cầu 90×90, `BaseMultiResolutionImage` dùng ảnh nào?
4. `MultiResolutionImage` tự kế thừa `Image` hay cần implementation đồng thời là `Image`?
5. Khi `Graphics2D` đã có transform HiDPI từ cửa sổ thật, vì sao không nên gọi thêm `scale(2,2)` vô điều kiện?
6. Tại sao unit test headless của `getResolutionVariant` vẫn chưa chứng minh icon hiển thị đúng trên màn hình 150%?
7. `ImageIO.read` tự ghép `save.png` và `save@2x.png` thành một đối tượng multi-resolution hay không?

**Gợi ý đáp án:** (1) raster 48×48 là nguồn có nhiều pixel hơn cho cùng icon logical; (2) 48×48 vì là ảnh đầu tiên đủ kích thước; (3) 72×72 vì không ảnh nào đủ 90; (4) interface không kế thừa `Image`, implementation phải hỗ trợ cả hai nếu muốn `drawImage`; (5) tránh nhân đôi phép scale; (6) policy render còn phụ thuộc nền tảng, transform và hint; (7) không, phải tạo bộ variants tường minh.

## Tài liệu API chính thức

- [Oracle Java SE 21 — MultiResolutionImage](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/image/MultiResolutionImage.html)
- [Oracle Java SE 21 — BaseMultiResolutionImage](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/image/BaseMultiResolutionImage.html)
- [Oracle Java SE 21 — AbstractMultiResolutionImage](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/image/AbstractMultiResolutionImage.html)
- [Oracle Java SE 21 — RenderingHints](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/RenderingHints.html)
- [Oracle Java SE 21 — Graphics2D](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/Graphics2D.html)
- [Oracle Java SE 21 — ImageIO](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/javax/imageio/ImageIO.html)

Cần giữ rõ ba tầng: **kích thước logic của giao diện**, **tập ảnh raster nguồn nhiều độ phân giải** và **cách Java2D chọn/vẽ ảnh trong thiết bị cụ thể**. Khi tách được ba tầng này, giao diện có thể sắc nét trên HiDPI mà không phá bố cục hoặc dựa vào giả định sai về scale.