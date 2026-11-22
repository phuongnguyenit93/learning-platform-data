# Nguyên tắc thay thế Liskov và các bất biến của hợp đồng

## Mục tiêu

Nguyên tắc thay thế Liskov (Liskov Substitution Principle, LSP) nói rằng một đối tượng của kiểu con phải có thể được dùng ở mọi nơi chương trình mong đợi kiểu cha mà vẫn giữ đúng hành vi đã cam kết. Đây là một phần của nguyên tắc SOLID, thường được phát biểu bằng ý tưởng: nếu `S` là kiểu con của `T`, có thể thay một đối tượng `T` bằng đối tượng `S` mà không làm hỏng tính đúng đắn của chương trình.

Trong Java, quan hệ `extends` hoặc `implements` chỉ chứng minh quan hệ kiểu ở mức cú pháp. Nó không tự chứng minh LSP. Một lớp có thể biên dịch thành công nhưng vẫn vi phạm hợp đồng hành vi mà lớp cha hoặc interface đã hứa với người gọi.

## 1. Hợp đồng hành vi gồm những gì?

Hợp đồng của một phương thức hoặc kiểu mô tả những điều người gọi được phép giả định và những gì phương thức phải đảm bảo.

- **Tiền điều kiện (precondition):** điều kiện đầu vào mà người gọi phải đáp ứng trước khi gọi phương thức.
- **Hậu điều kiện (postcondition):** điều kiện kết quả hoặc trạng thái mà phương thức cam kết sau khi thực hiện thành công.
- **Bất biến (invariant):** điều kiện phải luôn đúng đối với đối tượng ở những thời điểm được hợp đồng quy định, đặc biệt trước và sau các thao tác công khai.
- **Ràng buộc lịch sử (history constraint):** giới hạn các thay đổi trạng thái được phép theo thời gian; kiểu con không được tạo ra chuỗi chuyển trạng thái mà hợp đồng kiểu cha cấm.
- **Hành vi lỗi:** các ngoại lệ và điều kiện lỗi mà người gọi có thể gặp khi dùng đầu vào hợp lệ.

LSP yêu cầu kiểu con tôn trọng hợp đồng của kiểu cha. Một cách ghi nhớ hữu ích là:

1. Kiểu con không được siết chặt tiền điều kiện: mọi đầu vào hợp lệ với kiểu cha vẫn phải được chấp nhận bởi kiểu con.
2. Kiểu con không được làm yếu hậu điều kiện: mọi bảo đảm của kiểu cha vẫn phải đúng khi đối tượng thực tế là kiểu con.
3. Kiểu con phải giữ các bất biến mà kiểu cha công khai cam kết. Kiểu con có thể có thêm bất biến riêng, nhưng việc duy trì chúng không được phá vỡ hợp đồng của kiểu cha.
4. Kiểu con phải tôn trọng những chuyển đổi trạng thái mà người dùng kiểu cha được phép dựa vào.
5. Với đầu vào hợp lệ, kiểu con không nên phát sinh lỗi mới khiến lời gọi vốn hợp lệ theo hợp đồng kiểu cha trở thành thất bại.

Ví dụ, nếu hợp đồng kiểu cha cho phép gọi một phương thức với mọi số nguyên không âm, kiểu con không thể tự ý yêu cầu thêm rằng giá trị phải nhỏ hơn 100. Đó là siết chặt tiền điều kiện. Nếu kiểu cha cam kết rằng một thao tác thành công sẽ trả về một danh sách không rỗng, kiểu con không thể trả về danh sách rỗng trong trường hợp tương tự. Đó là làm yếu hậu điều kiện.

## 2. Ví dụ kinh điển: hình chữ nhật và hình vuông có thể thay thế nhau không?

Về toán học, hình vuông là một hình chữ nhật đặc biệt. Nhưng quan hệ “là một” trong mô hình miền nghiệp vụ chưa đủ để quyết định quan hệ kế thừa trong chương trình. Hãy xem một lớp hình chữ nhật có thể thay đổi chiều rộng và chiều cao độc lập.

Hợp đồng của lớp này nói rõ rằng `setWidth` chỉ thay đổi chiều rộng, còn chiều cao được giữ nguyên. Một lớp hình vuông kế thừa nó thường cố bảo đảm chiều rộng luôn bằng chiều cao bằng cách ghi đè cả hai setter. Điều đó duy trì bất biến của hình vuông, nhưng lại phá vỡ lời hứa của hình chữ nhật.

Lưu mã sau vào tệp `LiskovContractDemo.java`:

```java
public class LiskovContractDemo {
    public static void main(String[] args) {
        MutableRectangle rectangle = new MutableRectangle(4, 5);
        MutableRectangle squareAsRectangle = new MutableSquare(4);

        checkWidthSetterContract(rectangle);
        checkWidthSetterContract(squareAsRectangle);

        Shape rectangleShape = new RectangleShape(4, 5);
        Shape squareShape = new SquareShape(4);
        System.out.println("Shape model: rectangle area="
                + rectangleShape.area() + ", square area=" + squareShape.area());
    }

    // Hợp đồng Rectangle quy định setWidth không thay đổi chiều cao.
    private static void checkWidthSetterContract(MutableRectangle rectangle) {
        int heightBefore = rectangle.getHeight();
        rectangle.setWidth(10);
        int expectedArea = 10 * heightBefore;

        System.out.printf("%s: expected area=%d, actual area=%d%n",
                rectangle.getClass().getSimpleName(), expectedArea, rectangle.area());
    }

    static class MutableRectangle {
        private int width;
        private int height;

        MutableRectangle(int width, int height) {
            this.width = width;
            this.height = height;
        }

        public void setWidth(int width) {
            this.width = width;
        }

        public void setHeight(int height) {
            this.height = height;
        }

        public int getWidth() {
            return width;
        }

        public int getHeight() {
            return height;
        }

        public int area() {
            return width * height;
        }
    }

    static final class MutableSquare extends MutableRectangle {
        MutableSquare(int side) {
            super(side, side);
        }

        @Override
        public void setWidth(int width) {
            super.setWidth(width);
            super.setHeight(width);
        }

        @Override
        public void setHeight(int height) {
            super.setHeight(height);
            super.setWidth(height);
        }
    }

    interface Shape {
        int area();
    }

    record RectangleShape(int width, int height) implements Shape {
        RectangleShape {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("Dimensions must be non-negative");
            }
        }

        @Override
        public int area() {
            return width * height;
        }
    }

    record SquareShape(int side) implements Shape {
        SquareShape {
            if (side < 0) {
                throw new IllegalArgumentException("Side must be non-negative");
            }
        }

        @Override
        public int area() {
            return side * side;
        }
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```text
javac -encoding UTF-8 LiskovContractDemo.java
java LiskovContractDemo
```

Kết quả chuẩn:

```text
MutableRectangle: expected area=50, actual area=50
MutableSquare: expected area=40, actual area=100
Shape model: rectangle area=20, square area=16
```

Khi tham số là `MutableRectangle(4, 5)`, đặt chiều rộng thành 10 giữ nguyên chiều cao 5, nên diện tích là 50. Khi truyền `MutableSquare(4)` qua cùng kiểu tham chiếu `MutableRectangle`, lời gọi `setWidth(10)` cũng đổi chiều cao thành 10; diện tích trở thành 100 thay vì 40 như người gọi được phép kỳ vọng theo hợp đồng lớp cha. Chương trình vẫn biên dịch, nhưng hành vi đã vi phạm LSP.

## 3. Thiết kế lại bằng abstraction theo hành vi

Nếu người gọi chỉ cần biết diện tích, không nên yêu cầu mọi hình đều có các setter chiều rộng và chiều cao độc lập. Hãy mô tả hành vi chung bằng interface `Shape`, rồi để hình chữ nhật và hình vuông là hai kiểu riêng biệt. Phần cuối của chương trình trên minh họa cách này: cả hai kiểu đều có thể được dùng thông qua `Shape`, và hợp đồng chung chỉ yêu cầu cung cấp diện tích.

Cách thiết kế này giữ được đặc điểm riêng của từng kiểu:

- `RectangleShape` lưu chiều rộng và chiều cao độc lập.
- `SquareShape` lưu một cạnh, nên không thể rơi vào trạng thái có hai cạnh khác nhau.
- Cả hai đều đáp ứng hợp đồng `area()` và không cần giả vờ rằng các thao tác thay đổi kích thước của chúng có cùng ngữ nghĩa.

Một giải pháp khác là dùng composition thay vì kế thừa nếu hai lớp cần chia sẻ mã nhưng không có cùng hợp đồng hành vi. Kế thừa nên biểu diễn khả năng thay thế được, không chỉ là cách tái sử dụng một số trường hoặc phương thức.

## 4. Bất biến của kiểu cha và kiểu con

Bất biến giúp xác định trạng thái nào luôn phải đúng. Chẳng hạn, một tài khoản ngân hàng có thể yêu cầu số tài khoản không đổi sau khi tạo; một tập hợp có thể yêu cầu không chứa phần tử trùng lặp; một hình vuông yêu cầu hai cạnh bằng nhau.

Khi tạo kiểu con, hãy kiểm tra hai nhóm điều kiện:

- **Bất biến của kiểu cha:** vẫn phải đúng đối với mọi đối tượng kiểu con được dùng thông qua kiểu cha. Không được làm mất bảo đảm mà người gọi đã dựa vào.
- **Bất biến bổ sung của kiểu con:** được phép chặt chẽ hơn, miễn là kiểu con có thể duy trì chúng mà không thay đổi hành vi được hứa bởi kiểu cha.

Một bất biến riêng có thể khiến kế thừa trở nên bất khả thi. Trong ví dụ trên, hình vuông yêu cầu chiều rộng và chiều cao bằng nhau; lớp hình chữ nhật cho phép hai giá trị thay đổi độc lập. Khi cùng một đối tượng phải đáp ứng cả hai hợp đồng, hai yêu cầu xung đột. Đây là dấu hiệu nên thay đổi abstraction hoặc mô hình hóa các kiểu riêng qua một interface nhỏ hơn.

Không nên nhầm bất biến với tiền điều kiện. Bất biến mô tả trạng thái hợp lệ của đối tượng; tiền điều kiện mô tả điều người gọi phải đáp ứng cho một lời gọi cụ thể. Nếu kiểu con từ chối một lời gọi mà kiểu cha chấp nhận chỉ để bảo vệ bất biến riêng, thiết kế kế thừa có thể đã sai.

## 5. Cách đánh giá một quan hệ kế thừa trong Java

Với mỗi lớp con hoặc lớp triển khai interface, hãy tự hỏi:

1. **Đầu vào:** Có đầu vào nào hợp lệ theo hợp đồng kiểu cha nhưng bị kiểu con từ chối không?
2. **Kết quả:** Kiểu con có trả về kết quả yếu hơn, thiếu bảo đảm hoặc trạng thái khác với điều người gọi được hứa không?
3. **Trạng thái:** Sau một lời gọi hợp lệ, các bất biến công khai của kiểu cha còn đúng không?
4. **Chuỗi thao tác:** Có chuỗi thao tác nào hợp lệ với kiểu cha nhưng trở nên bất hợp lệ hoặc gây kết quả bất ngờ khi dùng kiểu con không?
5. **Ngoại lệ:** Kiểu con có ném ngoại lệ mới trong trường hợp mà hợp đồng kiểu cha hứa sẽ thành công không?
6. **Ngữ nghĩa:** Tên phương thức và hành vi thực tế của kiểu con có còn phù hợp với cách người gọi hiểu hợp đồng kiểu cha không?

Java có thể kiểm tra một phần quy tắc ghi đè ở mức ngôn ngữ. Ví dụ, phương thức ghi đè không thể giảm mức truy cập, kiểu trả về có thể tương thích theo quy tắc covariance, và không thể khai báo thêm checked exception rộng hơn những gì phương thức bị ghi đè cho phép. Tuy nhiên, trình biên dịch không thể chứng minh rằng tiền điều kiện, hậu điều kiện và bất biến về mặt nghiệp vụ đã được giữ nguyên. Vì thế, code biên dịch thành công chưa đủ để kết luận thiết kế tuân thủ LSP.

## 6. Thực hành để giữ hợp đồng ổn định

- **Viết rõ hợp đồng:** JavaDoc nên nêu điều kiện đầu vào, kết quả, ảnh hưởng lên trạng thái và ngoại lệ quan trọng của phương thức công khai.
- **Giữ interface nhỏ và có mục đích:** chỉ đưa vào interface những hành vi mà mọi kiểu triển khai đều có thể cung cấp với cùng ý nghĩa.
- **Ưu tiên bất biến khi phù hợp:** kiểu bất biến thường ít có rủi ro vi phạm ràng buộc lịch sử vì trạng thái không thay đổi sau khi tạo.
- **Dùng composition khi hợp đồng không tương thích:** chia sẻ triển khai không bắt buộc phải chia sẻ quan hệ kế thừa.
- **Kiểm thử hợp đồng:** chạy cùng một bộ kiểm thử hành vi trên lớp cơ sở và các lớp triển khai. Kiểm thử không chứng minh mọi trường hợp, nhưng có thể phát hiện các vi phạm thực tế như ví dụ hình chữ nhật/hình vuông.
- **Kiểm thử các chuỗi thao tác:** không chỉ kiểm tra một lời gọi riêng lẻ; hãy thử các trình tự thay đổi trạng thái mà người dùng kiểu cha được phép thực hiện.

## Ghi nhớ

LSP là nguyên tắc về hành vi: kiểu con phải giữ những cam kết mà người gọi được phép dựa vào khi làm việc với kiểu cha. Không siết chặt tiền điều kiện, không làm yếu hậu điều kiện, giữ bất biến và các chuyển đổi trạng thái hợp lệ. Nếu một lớp con phải phá hợp đồng của lớp cha để duy trì quy tắc riêng của nó, hãy cân nhắc dùng interface thể hiện hành vi chung, tách các abstraction hoặc chuyển sang composition thay vì cố ép quan hệ kế thừa.