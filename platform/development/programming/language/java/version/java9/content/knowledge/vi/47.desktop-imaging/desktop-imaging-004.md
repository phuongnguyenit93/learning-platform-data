# Đọc và ghi TIFF bằng Image I/O chuẩn trong Java 9+

## 1. TIFF là gì và vì sao Java 9 đáng chú ý?

**TIFF (Tagged Image File Format)** là định dạng ảnh dựa trên các trường thông tin (*tags*) mô tả kích thước, cách tổ chức điểm ảnh, kiểu màu, cách nén, độ phân giải và nhiều loại metadata. TIFF thường được dùng trong quét tài liệu, lưu trữ ảnh chất lượng cao, xử lý ảnh nhiều trang và những hệ thống cần giữ thông tin kỹ thuật của ảnh.

Khác với một tệp PNG thông thường chứa một ảnh, **một tệp TIFF có thể chứa nhiều ảnh/trang** (*multi-page TIFF*), mỗi trang có thể có kích thước, metadata và cách nén riêng.

Từ **JDK 9**, bộ plugin TIFF để **đọc và ghi** được tích hợp trong **Java Image I/O API chuẩn** của module `java.desktop`. Trong các JDK hiện đại, có thể sử dụng trực tiếp:

- `javax.imageio.ImageIO` để đọc/ghi **một ảnh** theo cách đơn giản.
- `javax.imageio.ImageReader` và `ImageWriter` để đọc/ghi **nhiều trang**, thiết lập codec, vùng ảnh và metadata.
- `javax.imageio.plugins.tiff` để làm việc với các trường TIFF như `TIFFDirectory`, `TIFFField`, `BaselineTIFFTagSet` và các bộ tag khác.

Với tác vụ TIFF phổ biến, bạn **không cần thư viện đọc TIFF cũ hoặc API nội bộ `com.sun.*`**. Tuy nhiên, hỗ trợ TIFF chuẩn không đồng nghĩa có thể xử lý mọi biến thể TIFF hoặc mọi loại nén/không gian màu. Khi có plugin bên thứ ba, khả năng hỗ trợ còn có thể phụ thuộc plugin thực tế được chọn.

Bài này dùng **Java 17+**, chỉ gọi API chuẩn còn hiện hành; các ví dụ cũng chạy trên JDK mới hơn.

## 2. Phân biệt một ảnh, nhiều trang, pixels và metadata

Hãy phân biệt bốn khái niệm:

| Thành phần | Ý nghĩa |
| --- | --- |
| `BufferedImage` | Dữ liệu ảnh trong bộ nhớ Java: pixels, raster, color model; **không đại diện cho toàn bộ tập trang hoặc mọi tag TIFF**. |
| `ImageIO.read(...)` | Tiện ích đọc **ảnh đầu tiên** mà reader hỗ trợ từ file/stream. |
| `ImageReader` | Bộ giải mã cung cấp thông tin từng ảnh: `getNumImages`, `getWidth`, `getHeight`, `read(index)`, `getImageMetadata(index)`. |
| `ImageWriter` | Bộ mã hóa có thể ghi một ảnh hoặc một chuỗi ảnh bằng `prepareWriteSequence` / `writeToSequence` / `endWriteSequence`. |
| `IIOMetadata`, `TIFFDirectory` | Đọc hoặc cấu hình các trường metadata của TIFF (chẳng hạn compression, resolution, orientation, Exif). |

Một cách hình dung:

```text
scan.tif
├── TIFF header
├── Image File Directory (IFD) trang 0
│   ├── Tags: kích thước, nén, màu, độ phân giải...
│   └── Pixel data trang 0
├── IFD trang 1
│   ├── Tags riêng của trang 1
│   └── Pixel data trang 1
└── ...
```

**IFD (Image File Directory)** là cấu trúc gắn các tag của một ảnh/trang. Nhiều TIFF có nhiều IFD được nối với nhau. Vì vậy, thao tác `ImageIO.read(file)` trả về **một `BufferedImage`**, không phải danh sách toàn bộ IFD và không bảo toàn mặc định metadata khi bạn ghi lại ảnh đó.

## 3. Cách nhanh nhất: đọc/ghi TIFF một trang

`ImageIO` chọn một plugin Image I/O đã đăng ký thông qua cơ chế SPI. Hai phương thức ngắn gọn:

```java
BufferedImage image = ImageIO.read(Path.of("source.tif").toFile());
if (image == null) {
    throw new IOException("Không có ImageReader phù hợp");
}

boolean written = ImageIO.write(
        image, "TIFF", Path.of("copy.tif").toFile());
if (!written) {
    throw new IOException("Không có ImageWriter TIFF");
}
```

**Đây là đoạn minh họa, không phải lớp Java độc lập**: cần import `java.awt.image.BufferedImage`, `java.nio.file.Path`, `javax.imageio.ImageIO`, `java.io.IOException` và phải có `source.tif` hợp lệ.

Ý nghĩa:

1. `ImageIO.read` phát hiện định dạng nhờ nội dung/file header khi có reader thích hợp. File chưa giải mã được có thể gây `IOException`; nếu không có reader phù hợp, có thể nhận `null`.
2. `ImageIO.write(image, "TIFF", file)` yêu cầu writer có tên định dạng `TIFF` và trả `false` nếu không tìm thấy writer; các lỗi I/O có thể ném exception.
3. `BufferedImage` chỉ giữ pixels/color model. **Không mong đợi metadata, tất cả trang, EXIF, orientation, ICC profile, DPI hoặc tag tùy biến tự được sao chép** khi `read` rồi `write` theo cách này.
4. Dạng `File` tiện cho bài học; với stream và tài nguyên cần điều khiển chặt, dùng `ImageInputStream` và `ImageOutputStream` cùng `try-with-resources`.

Khi cần xử lý TIFF nhiều trang hoặc điều khiển compression, chuyển sang API ở các mục tiếp theo.

## 4. Ví dụ hoàn chỉnh: tạo, đọc TIFF một trang và TIFF hai trang

Chương trình bên dưới **tự sinh dữ liệu ảnh**, ghi `single.tif` (một trang) và `pages.tif` (hai trang), sau đó đọc lại để xác minh kích thước và pixels. Không cần tải tệp mẫu, mở giao diện desktop, cài database hoặc thêm dependency.

Lưu toàn bộ mã vào **`TiffImageIODemo.java`**:

```java
import java.awt.image.BufferedImage;
import java.nio.file.Path;
import java.util.Iterator;
import javax.imageio.IIOImage;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.ImageWriter;
import javax.imageio.stream.ImageInputStream;
import javax.imageio.stream.ImageOutputStream;

public class TiffImageIODemo {
    public static void main(String[] args) throws Exception {
        BufferedImage first = solidImage(8, 6, 0x336699);
        BufferedImage second = solidImage(4, 3, 0xcc8844);

        Path single = Path.of("single.tif");
        if (!ImageIO.write(first, "TIFF", single.toFile())) {
            throw new IllegalStateException("TIFF writer unavailable");
        }
        BufferedImage readSingle = ImageIO.read(single.toFile());
        if (readSingle == null) {
            throw new IllegalStateException("TIFF reader unavailable");
        }
        System.out.println("Single page: " +
                readSingle.getWidth() + "x" + readSingle.getHeight());
        System.out.println("Single pixel matches: " +
                (readSingle.getRGB(0, 0) == first.getRGB(0, 0)));

        Path multi = Path.of("pages.tif");
        Iterator<ImageWriter> writers =
                ImageIO.getImageWritersByFormatName("TIFF");
        if (!writers.hasNext()) {
            throw new IllegalStateException("TIFF writer unavailable");
        }
        ImageWriter writer = writers.next();

        try (ImageOutputStream output =
                     ImageIO.createImageOutputStream(multi.toFile())) {
            if (output == null) {
                throw new IllegalStateException("No output stream");
            }
            writer.setOutput(output);
            if (!writer.canWriteSequence()) {
                throw new IllegalStateException(
                        "TIFF writer cannot write sequence");
            }

            writer.prepareWriteSequence(null);
            writer.writeToSequence(new IIOImage(first, null, null), null);
            writer.writeToSequence(new IIOImage(second, null, null), null);
            writer.endWriteSequence();
        } finally {
            writer.dispose();
        }

        try (ImageInputStream input =
                     ImageIO.createImageInputStream(multi.toFile())) {
            if (input == null) {
                throw new IllegalStateException("No input stream");
            }
            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new IllegalStateException("TIFF reader unavailable");
            }

            ImageReader reader = readers.next();
            try {
                reader.setInput(input, false, false);
                int pages = reader.getNumImages(true);
                BufferedImage page0 = reader.read(0);
                BufferedImage page1 = reader.read(1);

                System.out.println("Pages: " + pages);
                System.out.println("Page 0: " + page0.getWidth() +
                        "x" + page0.getHeight());
                System.out.println("Page 1: " + page1.getWidth() +
                        "x" + page1.getHeight());
                System.out.println("Page 1 pixel matches: " +
                        (page1.getRGB(0, 0) == second.getRGB(0, 0)));
            } finally {
                reader.dispose();
            }
        }
    }

    private static BufferedImage solidImage(int width, int height, int rgb) {
        BufferedImage image =
                new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                image.setRGB(x, y, rgb);
            }
        }
        return image;
    }
}
```

Trong thư mục trống chứa file Java, biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 TiffImageIODemo.java
java TiffImageIODemo
```

**Stdout chính xác** trên JDK có plugin TIFF chuẩn:

```text
Single page: 8x6
Single pixel matches: true
Pages: 2
Page 0: 8x6
Page 1: 4x3
Page 1 pixel matches: true
```

Sau khi chạy, thư mục có thêm hai file `single.tif` và `pages.tif`. Kết quả này được kiểm chứng bằng biên dịch `--release 17` và chạy trên OpenJDK 24.

### Hiểu cơ chế ghi

- `ImageIO.write(first, "TIFF", ...)` tạo **một trang**, không tự tạo sequence.
- `getImageWritersByFormatName("TIFF")` trả iterator writer; code kiểm tra `hasNext()` trước khi gọi `next()` để tránh giả định plugin luôn có mặt.
- `ImageIO.createImageOutputStream` tạo stream cho plugin, còn `writer.setOutput` gắn writer với stream đó.
- `writer.canWriteSequence()` kiểm tra khả năng ghi nhiều ảnh. Plugin TIFF chuẩn hiện đại hỗ trợ điều này.
- `prepareWriteSequence(null)` chuẩn bị container TIFF; `writeToSequence(new IIOImage(...), null)` thêm từng trang, với metadata và write param mặc định. `endWriteSequence()` đóng chuỗi, hoàn tất các cấu trúc liên kết cần thiết của TIFF.
- `writer.dispose()` giải phóng tài nguyên nội bộ của writer, còn `try-with-resources` đóng `ImageOutputStream`. Hai việc là **khác nhau**.

### Hiểu cơ chế đọc

- `ImageIO.getImageReaders(input)` tìm reader có thể nhận dạng nội dung của stream (không phụ thuộc tên đuôi file).
- `reader.setInput(input, false, false)` cấu hình stream có khả năng truy cập trang theo chỉ số, không chỉ “đọc tiến” và không bỏ qua metadata.
- `reader.getNumImages(true)` cho phép quét stream để biết số trang thực. Việc quét có thể tốn thời gian với file lớn.
- `reader.read(0)` và `reader.read(1)` đọc từng trang với chỉ số **bắt đầu từ 0**. Mỗi trang có thể có kích thước khác nhau.
- `reader.dispose()` giải phóng bộ giải mã; `ImageInputStream.close()` được `try-with-resources` đảm bảo ngay cả khi có exception.

**Lưu ý:** chương trình chỉ chạy minh họa trên một thư mục riêng. Trong production, phải xử lý lỗi I/O khi đang viết sequence (có thể còn file dở dang), tránh ghi đè file đã có và lưu kết quả tạm trước khi chuyển file vào vị trí chính thức.

## 5. Thứ tự API để xử lý TIFF nhiều trang

Để đọc tất cả trang, trình tự thông thường là:

```text
ImageInputStream
   → ImageIO.getImageReaders(input)
   → ImageReader.setInput(input)
   → ImageReader.getNumImages(true)
   → lặp index 0 .. pages-1
        ├── getWidth(index) / getHeight(index) trước khi giải mã
        ├── read(index[, param]) để lấy pixels
        └── getImageMetadata(index) nếu cần tags
   → reader.dispose() và đóng input
```

Để ghi nhiều trang:

```text
ImageOutputStream
   → ImageWriter.setOutput(output)
   → canWriteSequence()
   → prepareWriteSequence(null)
   → writeToSequence(IIOImage(page0), params)
   → writeToSequence(IIOImage(page1), params)
   → ...
   → endWriteSequence()
   → writer.dispose() và đóng output
```

Một số điểm dễ nhầm:

1. `ImageIO.read("pages.tif")` **chỉ đọc một ảnh**, thường là trang đầu. Nếu mục tiêu là quét hồ sơ nhiều trang, phải dùng `ImageReader` và duyệt các index.
2. `reader.getNumImages(false)` **có thể trả -1** nếu không thể biết số trang mà không quét; `true` cho phép quét khi cần. Không dùng `getNumImages(true)` nếu đã đặt `seekForwardOnly=true`, vì API có thể ném `IllegalStateException`.
3. Không mặc định tất cả writer đều ghi sequence; luôn kiểm tra `canWriteSequence()`.
4. Không giữ một loạt `BufferedImage` kích thước lớn trong bộ nhớ nếu chỉ cần xử lý trang một cách tuần tự. Có thể đọc và giải phóng từng trang tùy yêu cầu nghiệp vụ.
5. Nếu muốn giữ lại thông tin ảnh gốc, phải xử lý metadata từng trang, không chỉ ghi pixels.

## 6. Chọn nén TIFF bằng `ImageWriteParam`

TIFF là container hỗ trợ nhiều kiểu mã hóa dữ liệu ảnh. Nén có thể **không mất dữ liệu** (ví dụ LZW/Deflate/PackBits trong các cấu hình phù hợp) hoặc **có mất dữ liệu** (ví dụ JPEG-in-TIFF). Sự hỗ trợ phụ thuộc plugin, loại ảnh, bit depth và không gian màu; không được xem tất cả thuật toán là bắt buộc.

API chọn compression:

```java
ImageWriteParam param = writer.getDefaultWriteParam();
if (param.canWriteCompressed()) {
    String[] types = param.getCompressionTypes();
    if (types != null && Arrays.asList(types).contains("LZW")) {
        param.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
        param.setCompressionType("LZW");
    }
}
writer.write(null, new IIOImage(image, null, null), param);
```

Đây là **trích đoạn minh họa**, giả sử `writer` đã gắn `ImageOutputStream`, `image` là `BufferedImage` và đã import `ImageWriteParam`, `ImageWriter`, `IIOImage`, `Arrays`. Trình tự điều khiển cần nhớ:

- Gọi `canWriteCompressed()` trước.
- Lấy danh sách `getCompressionTypes()`; tên như `"LZW"` phải **khớp chính xác giá trị writer công bố**.
- Đặt `MODE_EXPLICIT` **trước khi** gọi `setCompressionType(...)`.
- Nếu writer không hỗ trợ `LZW`, chọn loại nén khác được công bố hoặc để mặc định, không ép chuỗi tùy ý.
- Với ảnh trắng đen 1-bit, fax compression có quy tắc riêng; với nhiều loại ảnh RGB, LZW/Deflate thường là lựa chọn bảo toàn pixel. Không kết luận về kích thước tệp trước khi đo thực tế.

### Ví dụ nén LZW và đọc tag nén — chương trình độc lập

Để kiểm chứng metadata, file sau **chỉ sử dụng thư viện JDK**. Lưu vào `TiffDetailsDemo.java`:

```java
import javax.imageio.*;
import javax.imageio.stream.*;
import javax.imageio.plugins.tiff.*;
import java.awt.image.BufferedImage;
import java.io.File;
import java.util.Arrays;

public class TiffDetailsDemo {
    public static void main(String[] args) throws Exception {
        BufferedImage image =
                new BufferedImage(8, 6, BufferedImage.TYPE_INT_RGB);
        image.setRGB(0, 0, 0x336699);

        File file = new File("lzw.tiff");
        ImageWriter writer =
                ImageIO.getImageWritersByFormatName("TIFF").next();

        try (ImageOutputStream output =
                     ImageIO.createImageOutputStream(file)) {
            writer.setOutput(output);
            ImageWriteParam param = writer.getDefaultWriteParam();

            System.out.println("Compression available: " +
                    param.canWriteCompressed());
            System.out.println("LZW available: " +
                    (param.getCompressionTypes() != null &&
                     Arrays.asList(param.getCompressionTypes())
                             .contains("LZW")));

            param.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
            param.setCompressionType("LZW");
            writer.write(null, new IIOImage(image, null, null), param);
        } finally {
            writer.dispose();
        }

        try (ImageInputStream input =
                     ImageIO.createImageInputStream(file)) {
            ImageReader reader = ImageIO.getImageReaders(input).next();
            try {
                reader.setInput(input);
                TIFFDirectory directory = TIFFDirectory.createFromMetadata(
                        reader.getImageMetadata(0));
                TIFFField tag = directory.getTIFFField(
                        BaselineTIFFTagSet.TAG_COMPRESSION);

                System.out.println("Compression tag: " + tag.getAsInt(0));
                System.out.println("Read pixel matches: " +
                        (reader.read(0).getRGB(0, 0) ==
                         image.getRGB(0, 0)));
            } finally {
                reader.dispose();
            }
        }
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 TiffDetailsDemo.java
java TiffDetailsDemo
```

Đầu ra trên **plugin TIFF chuẩn của OpenJDK 24**:

```text
Compression available: true
LZW available: true
Compression tag: 5
Read pixel matches: true
```

Trong TIFF chuẩn, **tag 259** (`Compression`) có giá trị **5** nghĩa là LZW. Chương trình lấy tag đó từ `reader.getImageMetadata(0)` rồi chuyển metadata thành `TIFFDirectory` để tra theo `BaselineTIFFTagSet.TAG_COMPRESSION`.

Ví dụ này **cố ý yêu cầu LZW** và giả định plugin chuẩn có writer/reader TIFF và hỗ trợ LZW. Khi áp dụng với plugin khác, nên chuyển thành kiểm tra `hasNext()` và hỗ trợ `LZW` như trích đoạn trước để đưa ra thông báo rõ ràng thay vì dựa vào `next()` hay `setCompressionType` luôn thành công.

## 7. Metadata TIFF: tag, DPI, định hướng, Exif và thông tin cần giữ lại

Khi đọc TIFF, pixels và metadata là hai nhánh thông tin:

```text
ImageReader
  ├── read(0)                 → BufferedImage: pixels
  └── getImageMetadata(0)     → IIOMetadata: tags
                                 ↓
                     TIFFDirectory.createFromMetadata(...)
                                 ↓
                           TIFFField theo mã tag
```

Các tag thường gặp:

| Tag hoặc thuộc tính | Ý nghĩa và điểm cần kiểm tra |
| --- | --- |
| `ImageWidth` / `ImageLength` | Chiều rộng/cao của trang. Có thể lấy nhanh hơn bằng `reader.getWidth(i)` / `getHeight(i)`. |
| `BitsPerSample` / `SamplesPerPixel` | Độ sâu của mỗi kênh màu, số kênh; liên quan `ColorModel` và độ chính xác màu. |
| `Compression` | Kiểu nén của trang, ví dụ 5 = LZW. |
| `PhotometricInterpretation` | Diễn giải mẫu pixel là grayscale, RGB hoặc kiểu khác. |
| `XResolution` / `YResolution` / `ResolutionUnit` | Độ phân giải in/quét; không đồng nghĩa kích thước pixel. |
| `Orientation` | Cách định hướng hiển thị; pixels giải mã không phải lúc nào đã được xoay theo ý người dùng. |
| Exif / GPS / ICC profile | Thông tin chụp, tọa độ hoặc quản lý màu; tùy file, plugin và bộ tag được hỗ trợ. |

API chuẩn `javax.imageio.plugins.tiff` cung cấp `TIFFDirectory` và các `TIFFTagSet`, giúp tránh thao tác trực tiếp cây DOM metadata một cách tùy tiện. `getImageMetadata(index)` trả `IIOMetadata` cho trang chỉ định, từ đó tra từng `TIFFField`. Khi cần ghi hoặc sửa tag, bạn có thể bắt đầu với `ImageWriter.getDefaultImageMetadata(...)`, chuyển sang `TIFFDirectory`, thay đổi field hợp lệ rồi chuyển về `IIOMetadata` bằng `getAsMetadata()` để cung cấp trong `IIOImage`.

**Không xem metadata là dữ liệu trang trí:** thay tag DPI, Orientation, ICC hay chứng cứ quy trình có thể làm thay đổi kết quả hiển thị/xử lý. Một thao tác “đọc ảnh rồi ghi ra file khác” mà bỏ `IIOMetadata` có thể **mất metadata gốc**. Với tài liệu scan hay file cần bảo toàn, hãy đối chiếu thông tin trước/sau, hoặc dùng quy trình giữ metadata được kiểm thử.

## 8. Đọc một vùng ảnh và giảm độ phân giải khi giải mã

Một TIFF lớn có thể có hàng chục nghìn pixel mỗi chiều. Thay vì dùng toàn bộ ảnh khi chỉ cần thumbnail hay vùng kiểm tra, `ImageReadParam` hỗ trợ:

- `setSourceRegion(Rectangle)`: chọn vùng hình chữ nhật nguồn.
- `setSourceSubsampling(xSub, ySub, 0, 0)`: lấy mẫu thưa theo bước ngang/dọc.
- `reader.getWidth(index)`, `getHeight(index)`: kiểm tra kích thước **trước khi** tạo ảnh có nhiều pixel.

Ví dụ trích đoạn (không độc lập; đã có `ImageReader reader` với input phù hợp và ảnh trang 0 ít nhất 800×600):

```java
ImageReadParam param = reader.getDefaultReadParam();
param.setSourceRegion(new Rectangle(100, 50, 400, 300));
param.setSourceSubsampling(2, 2, 0, 0);

BufferedImage preview = reader.read(0, param);
System.out.println(preview.getWidth() + "x" +
                   preview.getHeight()); // 200x150
```

Cần import `javax.imageio.ImageReadParam`, `java.awt.Rectangle`, `java.awt.image.BufferedImage`. Với vùng 400×300 và subsampling bước 2×2, kích thước đầu ra là 200×150.

Trước khi đặt `Rectangle`, hãy xác nhận vùng nằm trong kích thước nguồn, không có chiều rộng/cao bằng 0 và không tràn số nguyên. Phần nhỏ hơn được giải mã **không bảo đảm** codec sẽ không cần đọc/giải nén thêm các strip/tile chứa vùng đó; hiệu quả CPU/RAM phụ thuộc plugin và cấu trúc file. Với ảnh scan cực lớn, kiểm tra hạn mức memory và streaming thực tế.

## 9. Tổ chức tài nguyên và xử lý lỗi đúng cách

Đọc/ghi TIFF qua Image I/O có hai loại tài nguyên:

1. **Stream I/O**: `ImageInputStream` / `ImageOutputStream` nên đóng bằng `try-with-resources`.
2. **Codec instance**: `ImageReader` / `ImageWriter` có tài nguyên nội bộ và nên gọi `dispose()` trong `finally`.

`dispose()` không phải lệnh thay thế cho `ImageInputStream.close()` / `ImageOutputStream.close()`. Ngược lại, đóng stream mà quên `dispose()` cũng không phải mẫu an toàn cho plugin có tài nguyên riêng.

Đối với sequence:

- Gọi `prepareWriteSequence` một lần khi bắt đầu.
- Gọi `writeToSequence` theo đúng số trang.
- Gọi `endWriteSequence` sau trang cuối để kết thúc cấu trúc file.
- Nếu lỗi xảy ra khi đang ghi, file output có thể không hoàn chỉnh. Cần xóa tệp tạm hoặc để quy trình xử lý lỗi dọn dẹp; không đánh dấu file đã xuất bản thành công.
- Với file output đang có, xác định chính sách ghi đè. Ví dụ này dùng `Path.of(...)` đơn giản vì chạy trong thư mục trống; ứng dụng thật nên xử lý tên file, quyền truy cập, tính nhất quán và di chuyển tệp tạm một cách chủ động.

Cần phân biệt lỗi **không có plugin** (`iterator.hasNext()==false` hoặc `ImageIO.write(...)==false`), lỗi **nội dung file** (`IOException`/`IIOException`) và lỗi **cấu hình param** (`IllegalArgumentException`, `UnsupportedOperationException`). Cách xử lý phụ thuộc loại lỗi; không mặc định một file lỗi có thể sửa chỉ bằng đổi đuôi `.tif`.

## 10. Giới hạn và an toàn khi nhận TIFF từ nguồn không tin cậy

TIFF là định dạng linh hoạt, nên **sự hiện diện của plugin TIFF không bảo đảm đọc mọi kiểu TIFF**. Một số khác biệt cần xem xét:

- **Compression:** writer/reader thực tế có thể thiếu codec hoặc chỉ nhận kiểu nén trên ảnh một bit, RGB hoặc grayscale nhất định. Hỏi writer bằng `canWriteCompressed()` và `getCompressionTypes()`; kiểm thử file thật.
- **Color model và bit depth:** ảnh 1-bit, 8-bit, 16-bit, palette, CMYK, nhiều kênh, alpha hoặc ICC có thể cho ra `BufferedImage` khác nhau; không ép mọi thứ về `TYPE_INT_RGB` nếu cần giữ độ chính xác khoa học hoặc dữ liệu màu.
- **Multi-page và metadata:** đừng chỉ dùng `ImageIO.read`, đừng bỏ `IIOMetadata` khi công việc cần giữ thông tin; mỗi trang có thể khác kích thước/độ phân giải.
- **Biến thể TIFF mở rộng:** không tự giả định BigTIFF, GeoTIFF hay mọi tag chuyên biệt của thiết bị đều được plugin JDK hỗ trợ đầy đủ, kể cả khi lớp `GeoTIFFTagSet` có tồn tại.
- **Bảo mật và tài nguyên:** file chứa kích thước khai báo rất lớn, dữ liệu nén gây phình bộ nhớ, metadata không hợp lệ hoặc nhiều trang có thể tiêu tốn CPU, disk cache và RAM. Giới hạn kích thước file nhận vào, số trang, kích thước từng trang và tổng số pixel trước khi decode; xử lý timeout/quota ở tầng dịch vụ và cập nhật JDK định kỳ.
- **Metadata nhạy cảm:** Exif/GPS, tên người quét, thiết bị, vị trí hoặc thông tin quy trình có thể bị nhúng trong TIFF. Khi xuất bản ảnh, phải quyết định rõ giữ hay loại bỏ metadata theo yêu cầu nghiệp vụ.
- **Module runtime rút gọn:** plugin và API này thuộc `java.desktop`; khi tạo runtime bằng `jlink` cần có module tương ứng. Nếu dùng module Java tường minh, khai báo `requires java.desktop;`.

Một câu hỏi đúng trước khi triển khai là: cần **xem/biến đổi pixels** hay cần **bảo toàn file TIFF nguyên trạng** (tất cả trang, tags, màu, chứng cứ quét)? Hai yêu cầu này dẫn tới các chiến lược khác nhau.

## 11. Những nhầm lẫn hay gặp

| Vấn đề | Cách hiểu hoặc cách xử lý |
| --- | --- |
| “Java chỉ đọc PNG/JPEG, muốn TIFF phải tải plugin ngoài.” | Từ JDK 9, Java Image I/O chuẩn có TIFF reader và writer. Kiểm tra runtime/registry vì có thể bị thay đổi hoặc thêm plugin. |
| “`ImageIO.read(file)` lấy đủ mọi trang của TIFF.” | Không. Dùng `ImageReader` cùng `read(index)` để lấy từng trang. |
| “`ImageIO.write(..., "TIFF", file)` sẽ giữ mọi Exif/DPI.” | Không có bảo đảm. `BufferedImage` chủ yếu chứa pixels; quản lý `IIOMetadata` nếu cần giữ tags. |
| “`ImageIO.write` không ném exception thì chắc đã ghi.” | Với phương thức trả `boolean`, vẫn cần kiểm tra kết quả `false` khi thiếu writer; lỗi I/O có thể ném exception. |
| “`writer.writeToSequence` có thể gọi mà không chuẩn bị.” | Cần `canWriteSequence()` và `prepareWriteSequence(...)` trước, sau đó `endWriteSequence()`. |
| “`getNumImages(false)` luôn biết số trang.” | Có thể trả `-1`; dùng `getNumImages(true)` khi cần quét, hoặc đọc tuần tự có kiểm soát. |
| “Tên nén `LZW` dùng được với mọi writer.” | Kiểm tra `getCompressionTypes()` và loại pixel. |
| “`Compression=5` nghĩa là nén mất dữ liệu.” | Trong TIFF, 5 là LZW, cơ chế nén không mất dữ liệu. |
| “`dispose()` tự đóng file stream.” | Cần đóng stream I/O riêng bằng `try-with-resources`. |
| “Giữ pixels giống nhau tức là mọi thứ đã được bảo toàn.” | Tags, ICC, DPI, nhiều trang, loại pixel và cách nén có thể đã thay đổi. |
| “File TIFF không thể gây sự cố bộ nhớ vì được nén.” | Có thể gây cấp phát lớn sau giải nén; kiểm soát quota dựa trên số trang và kích thước. |

## 12. Checklist kiểm thử cho ứng dụng xử lý TIFF

Để đánh giá chức năng thay vì chỉ nhìn phần mở rộng:

1. **Khả năng:** `ImageIO.getImageReadersByFormatName("TIFF")` và `getImageWritersByFormatName("TIFF")` có provider không? Provider có hỗ trợ loại ảnh cần xử lý không?
2. **Pixels:** đọc lại trang đã ghi và so sánh kích thước, một tập pixel đại diện, color model và số kênh.
3. **Số trang:** với file nhiều trang, `getNumImages(true)` và `read(i)` có đúng thứ tự? Ảnh từng trang có đủ kích thước không?
4. **Compression:** kiểm tra các tên được hỗ trợ; ghi với mode tường minh, đọc lại tag `Compression` và xác minh kết quả.
5. **Metadata:** với bài toán cần giữ tag, so sánh resolution, orientation, ICC/Exif cùng tags bắt buộc trước/sau.
6. **Biên và lỗi:** thử file trống, không phải TIFF, TIFF hỏng, một trang lớn, nhiều trang lớn và file không có quyền ghi.
7. **Tài nguyên:** thử lặp nhiều lượt, xác nhận stream đóng, reader/writer dispose, quản lý file tạm và RAM/disk cache.
8. **Tương thích:** kiểm tra trên **JDK thật sẽ triển khai**, plugin SPI đang dùng và các công cụ bên ngoài phải trao đổi TIFF.

Câu hỏi tự kiểm tra: Nếu có một file TIFF 10 trang, muốn lấy trang thứ 7 thì gọi API nào? **`ImageReader.read(6)`** sau khi thiết lập input phù hợp. Nếu muốn giữ tag DPI khi xuất file khác, `ImageIO.read` rồi `ImageIO.write` đã đủ chưa? **Chưa**: cần đọc và ghi metadata theo cách được kiểm chứng.

## Tài liệu chính thức (API hiện hành)

- Java SE 26 — [`javax.imageio` package, danh sách format reader/writer chuẩn](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/package-summary.html): TIFF được hỗ trợ đọc và ghi.
- Java SE 26 — [`javax.imageio.plugins.tiff`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/plugins/tiff/package-summary.html): package TIFF có từ Java 9, gồm `TIFFDirectory`, `TIFFField`, `TIFFTagSet` và `TIFFImageReadParam`.
- Java SE 26 — [`ImageReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/ImageReader.html): số ảnh, chỉ số trang, nguồn input, giới hạn `seekForwardOnly` và metadata.
- Java SE 26 — [`ImageWriter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/ImageWriter.html): ghi ảnh, ghi sequence, metadata và tài nguyên.
- Java SE 26 — [`ImageWriteParam`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/ImageWriteParam.html): chọn mode nén, compression type, tiling và subsampling.
- Java SE 26 — [`TIFFDirectory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/plugins/tiff/TIFFDirectory.html): truy cập từng tag và chuyển đổi metadata.

**Ghi nhớ:** Với TIFF một trang, `ImageIO.read/write` giúp bắt đầu nhanh. Với TIFF **nhiều trang, nén tường minh, metadata hoặc kiểm soát tài nguyên**, sử dụng `ImageReader`/`ImageWriter` và stream chuẩn, luôn kiểm tra khả năng plugin và đọc lại kết quả đã ghi.