# Áp dụng MVC với JavaFX và ranh giới của FXML

## 1. JavaFX có thể tổ chức theo MVC như thế nào?

JavaFX cung cấp các thành phần giao diện như `Stage`, `Scene`, `Node`, control và cơ chế binding property. FXML cho phép mô tả cây giao diện bằng XML; `FXMLLoader` đọc cấu trúc đó, tạo các node và kết nối chúng với controller. Những cơ chế này có thể được tổ chức theo Model–View–Controller (MVC) để giao diện, điều phối tương tác và nghiệp vụ giữ các trách nhiệm riêng.

Trong một ứng dụng quản lý sách:

- **Model** biểu diễn dữ liệu và quy tắc nghiệp vụ. Trong ứng dụng phân tầng, Controller thường gọi Application Service; Service phối hợp Domain Model và Repository để thực hiện use case.
- **View** là cây node JavaFX, layout, control và style. FXML thường mô tả phần cấu trúc của View.
- **Controller** nhận sự kiện từ View, đọc input, gọi use case, chuyển kết quả thành trạng thái hiển thị và cập nhật View.

Luồng tương tác điển hình:

~~~mermaid
flowchart TD
    U[Người dùng] --> V[View: FXML và JavaFX Nodes]
    V -->|Action / input| C[JavaFX Controller]
    C -->|Command / use case| S[Application Service]
    S --> M[Domain Model và Repository]
    M --> S
    S -->|Kết quả / lỗi có nghĩa| C
    C -->|Cập nhật property và control| V
~~~

JavaFX không bắt buộc một kiến trúc MVC duy nhất. `FXMLLoader` chỉ hỗ trợ nạp View và kết nối controller; nó không tự tạo ranh giới nghiệp vụ. Cách tổ chức MVC đến từ việc thiết kế class, dependency và luồng dữ liệu của ứng dụng.

## 2. FXML là gì và không phải là gì?

FXML là định dạng XML mô tả object graph, thường là cây node giao diện JavaFX. Một file FXML có thể khai báo layout, control, thuộc tính, liên kết `fx:id`, controller và các event handler.

FXML phù hợp để mô tả:

- Cấu trúc `VBox`, `HBox`, `BorderPane`, `GridPane` và các layout khác.
- TextField, Button, Label, TableView, Menu và control tương tác.
- Thuộc tính như spacing, padding, prompt text, text và style class.
- `fx:id` để controller truy cập node được inject.
- Event handler như `onAction="#handleSave"` để chuyển sự kiện đến controller.

FXML không nên trở thành nơi chứa:

- Quy tắc nghiệp vụ như tính giá, duyệt đơn hoặc kiểm tra quyền.
- Truy vấn database, gọi HTTP client hoặc đọc secret.
- Quy trình điều phối nhiều use case.
- Logic phức tạp phụ thuộc trạng thái miền.

FXML là phần khai báo View. Controller là điểm nối giữa View và use case. Model/Service bảo vệ quy tắc và trạng thái nghiệp vụ. Việc đặt một đoạn mã trong controller hay FXML không tự làm nó trở thành logic trình bày; cần xét trách nhiệm mà đoạn mã đang thực hiện.

## 3. Cấu trúc package gợi ý

Một cấu trúc nhỏ có thể tách theo chức năng và tầng:

~~~text
src/main/java/
  com/example/library/
    domain/
      Book.java
      Isbn.java
    application/
      CreateBookUseCase.java
      CreateBookCommand.java
      DuplicateIsbnException.java
    infrastructure/
      JpaBookRepository.java
    ui/
      BookFormController.java
      BookListController.java
      ViewLoader.java
src/main/resources/
  com/example/library/ui/
    book-form.fxml
    book-list.fxml
    book-form.css
~~~

Đây là cách phân chia minh họa, không phải cấu trúc thư mục bắt buộc. Với ứng dụng lớn, có thể tổ chức theo feature như `books`, `members`, `loans`, bên trong mỗi feature vẫn tách domain/application/ui/infrastructure theo mức cần thiết.

Điểm cần giữ là class miền không phụ thuộc `javafx.scene.*` hoặc FXML; Controller không trực tiếp chứa SQL; FXML không tham chiếu đến repository hoặc service để tự thực hiện nghiệp vụ.

## 4. Tạo View bằng FXML

Ví dụ `book-form.fxml` mô tả form tạo sách:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<?import javafx.geometry.Insets?>
<?import javafx.scene.control.Button?>
<?import javafx.scene.control.Label?>
<?import javafx.scene.control.TextField?>
<?import javafx.scene.layout.VBox?>

<VBox xmlns:fx="http://javafx.com/fxml"
      fx:controller="com.example.library.ui.BookFormController"
      spacing="10">
    <padding>
        <Insets top="16" right="16" bottom="16" left="16" />
    </padding>
    <Label text="Tạo sách mới" styleClass="page-title" />
    <TextField fx:id="titleField" promptText="Tiêu đề sách" />
    <Label fx:id="titleErrorLabel" styleClass="field-error" />
    <TextField fx:id="isbnField" promptText="ISBN" />
    <Label fx:id="isbnErrorLabel" styleClass="field-error" />
    <Button text="Lưu" onAction="#handleSave" />
    <Label fx:id="statusLabel" />
</VBox>
~~~

`fx:controller` chỉ định class controller gắn với file FXML. Mỗi `fx:id` tương ứng với một field có tên phù hợp trong controller. `onAction="#handleSave"` yêu cầu FXMLLoader kết nối event của Button với phương thức handler được đánh dấu `@FXML`.

Không cần viết `fx:id` cho mọi node. Chỉ đặt ID cho node mà controller hoặc cơ chế binding cần truy cập. Các thuộc tính bố cục thuần túy có thể nằm trong FXML để tránh làm controller phải thiết lập từng chi tiết giao diện.

## 5. Controller nhận sự kiện và gọi use case

Controller thường có hai nhóm dependency:

- Dependency do FXMLLoader inject như `TextField`, `Label` và `Button` qua `@FXML`.
- Dependency ứng dụng như `CreateBookUseCase`, được cung cấp qua constructor hoặc factory.

Ví dụ hợp đồng use case:

~~~java
public record CreateBookCommand(String title, String isbn) {}

public interface CreateBookUseCase {
    void create(CreateBookCommand command);
}

public class DuplicateIsbnException extends RuntimeException {
    public DuplicateIsbnException() {
        super("ISBN đã tồn tại");
    }
}
~~~

Controller:

~~~java
package com.example.library.ui;

import com.example.library.application.CreateBookCommand;
import com.example.library.application.CreateBookUseCase;
import com.example.library.application.DuplicateIsbnException;
import javafx.fxml.FXML;
import javafx.scene.control.Label;
import javafx.scene.control.TextField;

public final class BookFormController {
    private final CreateBookUseCase createBook;

    @FXML
    private TextField titleField;

    @FXML
    private TextField isbnField;

    @FXML
    private Label titleErrorLabel;

    @FXML
    private Label isbnErrorLabel;

    @FXML
    private Label statusLabel;

    public BookFormController(CreateBookUseCase createBook) {
        this.createBook = createBook;
    }

    @FXML
    private void initialize() {
        titleErrorLabel.setText("");
        isbnErrorLabel.setText("");
        statusLabel.setText("");
    }

    @FXML
    private void handleSave() {
        clearErrors();

        String title = titleField.getText();
        String isbn = isbnField.getText();

        // Kiểm tra đơn giản để phản hồi sớm ngay trên form.
        if (title == null || title.isBlank()) {
            titleErrorLabel.setText("Vui lòng nhập tiêu đề.");
            return;
        }
        if (isbn == null || isbn.isBlank()) {
            isbnErrorLabel.setText("Vui lòng nhập ISBN.");
            return;
        }

        try {
            createBook.create(new CreateBookCommand(title.trim(), isbn.trim()));
            statusLabel.setText("Đã tạo sách thành công.");
        } catch (DuplicateIsbnException exception) {
            isbnErrorLabel.setText("ISBN này đã được sử dụng.");
        }
    }

    private void clearErrors() {
        titleErrorLabel.setText("");
        isbnErrorLabel.setText("");
        statusLabel.setText("");
    }
}
~~~

Đoạn mã giả định use case đã được triển khai và ném `DuplicateIsbnException` khi ISBN bị trùng. Controller kiểm tra rỗng để phản hồi nhanh, nhưng use case và Domain Model vẫn phải kiểm tra invariant vì cùng chức năng có thể được gọi từ API, import hoặc tác vụ nền.

Controller không tự tạo `CreateBookUseCase`, không biết database nào được dùng và không tự thực hiện câu SQL. Nó chuyển input thành command, gọi use case và ánh xạ kết quả có ý nghĩa thành trạng thái hiển thị.

## 6. FXMLLoader và thời điểm inject controller

Khi nạp FXML, FXMLLoader thực hiện các bước chính:

1. Đọc file FXML và tạo các node trong cây giao diện.
2. Tạo controller được chỉ định bởi `fx:controller`.
3. Inject các node có `fx:id` vào field tương ứng được đánh dấu `@FXML`.
4. Gọi phương thức `initialize()` sau khi các field FXML đã được inject.
5. Trả về root node để ứng dụng gắn vào Scene hoặc container.

Vì constructor chạy trước khi các field `@FXML` được inject, không truy cập `titleField`, `statusLabel` hoặc node khác trong constructor. Hãy dùng constructor để nhận dependency ứng dụng; dùng `initialize()` để cấu hình control, binding và listener cần node đã được inject.

Ví dụ nạp FXML:

~~~java
FXMLLoader loader = new FXMLLoader(
        getClass().getResource("/com/example/library/ui/book-form.fxml"));
Parent root = loader.load();
Scene scene = new Scene(root);
stage.setScene(scene);
stage.show();
~~~

Nếu file không tồn tại, `getResource(...)` có thể trả `null` và việc nạp sẽ thất bại. Hãy kiểm tra resource path và bảo đảm FXML được đóng gói vào classpath/module path.

## 7. Tiêm dependency cho Controller qua controllerFactory

Mặc định, nếu FXML khai báo `fx:controller`, FXMLLoader cần cách tạo controller phù hợp; cách mặc định thường yêu cầu constructor không tham số. Khi controller cần constructor injection, cung cấp `controllerFactory`.

~~~java
FXMLLoader loader = new FXMLLoader(
        getClass().getResource("/com/example/library/ui/book-form.fxml"));

loader.setControllerFactory(controllerType -> {
    if (controllerType == BookFormController.class) {
        return new BookFormController(createBookUseCase);
    }
    throw new IllegalArgumentException(
            "Controller chưa được đăng ký: " + controllerType.getName());
});

Parent root = loader.load();
~~~

`createBookUseCase` được tạo ở composition root hoặc lấy từ DI container của ứng dụng. Factory quyết định controller nào được tạo và dependency nào được cung cấp. Với nhiều màn hình, nên dùng một factory/DI container có cấu hình rõ thay vì viết nhiều nhánh rải rác.

Nếu dùng Spring, Guice hoặc container khác, controllerFactory có thể ủy quyền việc tạo bean cho container. Cần chọn scope phù hợp: controller gắn với một màn hình thường nên là instance riêng cho lần nạp màn hình đó, tránh dùng singleton controller chứa state của từng form.

Không đồng thời khai báo `fx:controller` trong FXML và gọi `loader.setController(...)` cho cùng lần nạp. Nếu tự gọi `setController`, bỏ `fx:controller` khỏi FXML; nếu giữ `fx:controller`, dùng `controllerFactory` để kiểm soát việc tạo.

## 8. Ranh giới của FXML và Controller

FXML và Controller cùng thuộc presentation layer nhưng có vai trò khác nhau:

| Trách nhiệm | Nơi phù hợp |
|---|---|
| Khai báo layout, control, label, style class | FXML |
| Khai báo `fx:id` và nối event handler | FXML |
| Đọc input từ control và chuyển thành command | Controller |
| Hiển thị lỗi theo trường hoặc trạng thái loading | Controller/View |
| Bind property đơn giản và định dạng hiển thị | FXML hoặc Controller tùy độ phức tạp |
| Điều phối use case | Application Service được Controller gọi |
| Kiểm tra invariant và chuyển trạng thái miền | Domain Model/Application layer |
| Truy vấn database hoặc gọi dịch vụ ngoài | Repository/gateway ở infrastructure |
| Xác thực và phân quyền | Security/application policy ở server-side boundary |

Không đặt truy vấn hoặc quy tắc nghiệp vụ trong `onAction` của FXML. Event handler chỉ nên trỏ đến phương thức controller có tên diễn đạt thao tác, ví dụ `handleSave`, `handleSearch` hoặc `handleCancel`.

Controller cũng không nên trở thành một “God Controller”. Nếu một màn hình có nhiều thao tác phức tạp, chuyển điều phối nghiệp vụ vào use case riêng, tách mapper hoặc presentation model, và để controller giữ vai trò cầu nối.

## 9. Model không nên phụ thuộc JavaFX Property

JavaFX cung cấp `StringProperty`, `IntegerProperty`, `BooleanProperty`, `ObservableList` và nhiều loại observable khác. Chúng hữu ích cho binding giao diện, nhưng không có nghĩa mọi Domain Entity nên dùng các kiểu này.

Ví dụ, có thể giữ Domain Model thuần Java:

~~~java
public final class Book {
    private final BookId id;
    private String title;

    public Book(BookId id, String title) {
        this.id = id;
        this.title = title;
    }

    public BookId id() { return id; }
    public String title() { return title; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không hợp lệ");
        }
        this.title = newTitle.trim();
    }
}
~~~

Ở presentation layer, có thể tạo View Model dùng JavaFX property:

~~~java
import javafx.beans.property.SimpleStringProperty;
import javafx.beans.property.StringProperty;

public final class BookRowViewModel {
    private final StringProperty title = new SimpleStringProperty();

    public BookRowViewModel(String title) {
        this.title.set(title);
    }

    public StringProperty titleProperty() {
        return title; 
    }
}
~~~

Controller hoặc mapper chuyển Domain Model thành View Model. Cách tách này giúp Domain Model không phụ thuộc JavaFX, dễ kiểm thử và có thể dùng lại ở REST API hoặc batch job. Với ứng dụng nhỏ, có thể bind trực tiếp một DTO đơn giản; hãy tránh để framework UI lan vào toàn bộ mô hình miền khi không có nhu cầu rõ ràng.

## 10. Binding dữ liệu cho TableView

Với màn hình danh sách, Controller có thể nhận `ObservableList` hoặc View Model và gắn dữ liệu vào TableView. Ví dụ:

~~~java
@FXML
private TableView<BookRowViewModel> bookTable;

@FXML
private TableColumn<BookRowViewModel, String> titleColumn;

@FXML
private void initialize() {
    titleColumn.setCellValueFactory(
            cell -> cell.getValue().titleProperty());
}

private void showBooks(List<Book> books) {
    ObservableList<BookRowViewModel> rows = FXCollections.observableArrayList(
            books.stream()
                    .map(book -> new BookRowViewModel(book.title()))
                    .toList());
    bookTable.setItems(rows);
}
~~~

Ví dụ cần các import JavaFX collection/control và `java.util.List`. `cellValueFactory` xác định property dùng để hiển thị trong cột. Việc lấy danh sách sách nên được thực hiện qua use case; `showBooks` chỉ chuyển dữ liệu thành dạng trình bày và cập nhật control.

Không để TableView giữ trực tiếp một tập Entity có thể bị chỉnh sửa tùy ý nếu điều đó làm lộ trạng thái miền. Khi người dùng chọn một dòng và nhấn Xóa, Controller lấy ID từ row model rồi gọi use case; Service tải đối tượng và kiểm tra quyền/trạng thái trước khi thay đổi.

## 11. CSS và tài nguyên giao diện

CSS JavaFX điều khiển phong cách của node như màu sắc, font, khoảng cách và trạng thái pseudo-class. Có thể đặt style class trong FXML:

~~~xml
<Label text="Tiêu đề sách" styleClass="field-label" />
<Label fx:id="titleErrorLabel" styleClass="field-error" />
~~~

Rồi gắn stylesheet vào Scene hoặc root:

~~~java
scene.getStylesheets().add(
        getClass().getResource("book-form.css").toExternalForm());
~~~

CSS nên mô tả diện mạo và trạng thái trực quan. Không đặt quy tắc nghiệp vụ trong stylesheet. Có thể dùng pseudo-class hoặc style class để thể hiện trạng thái lỗi/disabled, còn Controller hoặc View Model quyết định trạng thái đó dựa trên kết quả use case.

Đường dẫn FXML, CSS, ảnh và icon nên được nạp như classpath/module resources. Không ghép đường dẫn file từ input người dùng. Với ứng dụng modular, package chứa controller cần được mở cho `javafx.fxml` để FXMLLoader truy cập các field và method `@FXML` bằng reflection.

## 12. Xử lý tác vụ lâu bằng Task và Service

JavaFX có một Application Thread chịu trách nhiệm xử lý event và cập nhật scene graph. Không chạy truy vấn database, gọi HTTP hoặc xử lý tệp lớn đồng bộ trên thread này, vì giao diện sẽ bị đứng cho đến khi công việc hoàn tất.

Dùng `Task` để chạy công việc nền và cập nhật giao diện trong callback được thực thi trên JavaFX Application Thread:

~~~java
Task<BookDetails> task = new Task<>() {
    @Override
    protected BookDetails call() {
        return bookQuery.findDetails(bookId);
    }
};

task.setOnSucceeded(event -> {
    BookDetails details = task.getValue();
    titleLabel.setText(details.title());
    statusLabel.setText("Đã tải dữ liệu.");
});

task.setOnFailed(event -> {
    statusLabel.setText("Không thể tải dữ liệu.");
    logger.warn("Load book failed", task.getException());
});

executor.execute(task);
~~~

Ví dụ giả định `bookQuery`, `bookId`, `titleLabel`, `statusLabel`, `logger` và `executor` đã được cung cấp. `call()` chạy trên worker thread; các handler `setOnSucceeded` và `setOnFailed` được gọi trên JavaFX Application Thread nên có thể cập nhật control an toàn. Không gọi `titleLabel.setText(...)` trực tiếp bên trong `call()`.

Với tác vụ có thể tái sử dụng và cần trạng thái READY/SCHEDULED/RUNNING/SUCCEEDED/FAILED, JavaFX `Service` có thể quản lý việc tạo và chạy `Task`. Dù dùng `Task` hay `Service`, cần xử lý hủy tác vụ, lỗi và trường hợp màn hình đã đóng trước khi kết quả về.

## 13. Điều hướng giữa các màn hình

Không nên để Controller của màn hình A tự tìm và thao tác trực tiếp vào mọi node của màn hình B. Cách này tạo coupling giữa các View và khiến việc thay layout trở nên khó khăn.

Có thể dùng một thành phần điều hướng hoặc screen coordinator chịu trách nhiệm nạp FXML, tạo controller và thay Scene/root. Controller chỉ phát yêu cầu điều hướng sau khi use case hoàn tất.

Ví dụ hợp đồng:

~~~java
public interface Navigator {
    void showBookDetails(BookId id);
    void showBookList();
}
~~~

`Navigator` là abstraction của presentation/application boundary. Implementation biết FXML resource, Stage hoặc Scene hiện tại; controller chỉ yêu cầu chuyển màn hình. Với ứng dụng nhỏ, có thể dùng một lớp `ViewLoader` hoặc `ScreenManager` thay vì xây dựng navigation framework lớn.

## 14. Kiểm thử MVC JavaFX

Cần kiểm tra riêng các trách nhiệm:

| Phạm vi | Nội dung cần kiểm tra |
|---|---|
| Domain Model | Invariant và hành vi nghiệp vụ không phụ thuộc JavaFX |
| Application Service | Use case, transaction và quy tắc phối hợp |
| Controller | Input được chuyển thành command đúng; kết quả/lỗi được ánh xạ thành trạng thái View |
| FXML loading | File hợp lệ, controller được tạo, `fx:id` được inject và handler được kết nối |
| View binding | Property và collection hiển thị đúng trong control |
| End-to-end UI | Người dùng thao tác qua màn hình và nhận kết quả đúng |

Controller có thể unit test bằng cách tiêm fake/mock use case và một abstraction cho phần cập nhật View. Nếu controller trực tiếp sử dụng control JavaFX, test có thể khởi tạo JavaFX toolkit và nạp FXML bằng FXMLLoader để xác minh injection cùng event wiring.

Ví dụ test nạp FXML:

~~~java
FXMLLoader loader = new FXMLLoader(
        getClass().getResource("/com/example/library/ui/book-form.fxml"));
loader.setControllerFactory(type ->
        new BookFormController(fakeCreateBookUseCase));
Parent root = loader.load();
BookFormController controller = loader.getController();

assertNotNull(root);
assertNotNull(controller);
~~~

Đây là kiểm tra tích hợp tối thiểu cho resource và controller construction; để kiểm tra thao tác nút hoặc binding thực tế, cần khởi tạo JavaFX toolkit và chạy tương tác trên JavaFX Application Thread. Môi trường CI headless có thể cần cấu hình toolkit/display ảo hoặc dùng test framework JavaFX phù hợp.

Không nên kiểm tra mọi chi tiết pixel trong unit test Controller. Test layout/visual regression thuộc lớp UI test riêng; test controller tập trung vào điều phối và ánh xạ trạng thái.

## 15. Java Module System và quyền truy cập FXML

Nếu ứng dụng dùng Java Platform Module System, FXMLLoader cần quyền truy cập reflective vào package controller. `module-info.java` thường cần khai báo các module JavaFX và mở package UI cho `javafx.fxml`:

~~~java
module com.example.library {
    requires javafx.controls;
    requires javafx.fxml;

    exports com.example.library;
    opens com.example.library.ui to javafx.fxml;
}
~~~

`opens` cho phép FXMLLoader truy cập các thành phần `@FXML` không public trong package được chỉ định. Nếu thiếu khai báo này, ứng dụng modular có thể gặp lỗi reflective access khi nạp FXML. Chỉ mở package cần thiết; không mở toàn bộ module một cách tùy tiện.

## 16. Những sai lầm thường gặp

- **Đặt nghiệp vụ trong FXML handler hoặc Controller:** các quy tắc có thể bị bỏ qua khi use case được gọi từ nơi khác.
- **Để Controller tự tạo Service:** khó thay thế dependency và kiểm thử.
- **Truy cập field `@FXML` trong constructor:** các node chưa được FXMLLoader inject ở thời điểm đó.
- **Dùng `fx:controller` đồng thời với `setController`:** hai cơ chế tạo controller xung đột trong cùng lần nạp.
- **Không dùng controllerFactory khi cần constructor injection:** FXMLLoader mặc định không biết dependency ứng dụng phải lấy từ đâu.
- **Dùng singleton controller cho nhiều cửa sổ:** state và node của các màn hình có thể bị dùng chung ngoài ý muốn.
- **Đưa JavaFX Property vào Domain Model chỉ để binding:** làm miền phụ thuộc framework UI.
- **Chạy truy vấn hoặc HTTP đồng bộ trên JavaFX Application Thread:** giao diện bị treo.
- **Cập nhật control từ background thread:** vi phạm quy tắc thread của JavaFX và có thể gây lỗi khó tái hiện.
- **Để controller màn hình này truy cập node của màn hình khác:** tạo coupling và khó thay đổi giao diện.
- **Đặt dữ liệu người dùng hoặc secret trong resource public:** có thể làm lộ nội dung qua URL tĩnh.
- **Quên `opens ... to javafx.fxml` trong ứng dụng modular:** FXMLLoader không thể inject field hoặc gọi handler cần thiết.

## 17. Kết luận

JavaFX có thể triển khai MVC bằng cách dùng FXML mô tả View, Controller nhận sự kiện và điều phối use case, còn Model/Application layer giữ dữ liệu cùng quy tắc nghiệp vụ. `FXMLLoader` tạo node, tạo controller, inject field `@FXML` rồi gọi `initialize()`; `controllerFactory` cho phép cung cấp dependency qua constructor.

Giữ FXML ở vai trò khai báo giao diện, Controller ở vai trò chuyển tiếp giữa giao diện và use case, và Model không phụ thuộc JavaFX. Dùng property binding cho trạng thái trình bày, `Task` hoặc `Service` cho công việc nền, navigation coordinator cho điều hướng và test riêng cho controller, FXML cùng UI. Những ranh giới này giúp giao diện dễ thay đổi, nghiệp vụ dễ kiểm thử và ứng dụng JavaFX không bị khóa vào cấu trúc của một màn hình.
