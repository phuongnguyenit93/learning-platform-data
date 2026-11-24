# ModelAndViewAssert for View-Returning Controllers

In Spring MVC, a controller can return a ModelAndView to specify the view name and the data to place in the model. When testing this kind of controller, you need to verify that the controller selects the right view and supplies the expected model attributes for that view.

Spring Test provides the ModelAndViewAssert utility in the org.springframework.test.web package. Its methods verify the view name, the presence and values of model attributes, and list contents in the model. This utility is especially handy when a test already holds a ModelAndView object and wants to express assertions focused on the view and model.

## 1. Understanding the ModelAndView object

ModelAndView combines two parts:

- **Model:** the collection of data attributes the view can use for rendering.
- **View:** a logical view name or a View object Spring will use to render the response.

Example:

~~~java
@GetMapping("/books")
public ModelAndView listBooks() {
    ModelAndView mav = new ModelAndView("books/list");
    mav.addObject("pageTitle", "Books");
    mav.addObject("books", bookService.findAll());
    return mav;
}
~~~

In this example:

- books/list is the logical view name.
- pageTitle is a model attribute with the value Books.
- books is the list of data added to the model.
- Spring's view resolver finds the view corresponding to books/list based on application configuration.

A logical view name is usually not a template file path. With Thymeleaf, for instance, books/list might map to a template such as templates/books/list.html. With JSP, a view resolver might add a prefix and suffix to build the JSP path. This mapping depends on the view resolver configuration.

A controller can also return a ModelAndView by passing the view name and model into its constructor, or return a View object directly. When a controller returns a view object instead of a view name, getViewName() may return null; in that case, asserting on the view name is not the right check.

## 2. What is ModelAndViewAssert used for?

ModelAndViewAssert is a test utility class with static methods. It accepts a ModelAndView object and asserts the required properties.

Common assertions:

| Method | Purpose |
|---|---|
| assertViewName(mav, expectedName) | Verifies the logical view name |
| assertModelAttributeAvailable(mav, modelName) | Verifies the model contains the requested attribute |
| assertModelAttributeValue(mav, modelName, expectedValue) | Compares the value of a model attribute |
| assertModelAttributeValues(mav, expectedModel) | Verifies all expected name/value pairs in the map exist in the model and are equal |
| assertCompareListModelAttribute(mav, modelName, expectedList) | Compares each element of a list in the model in order |
| assertSortAndCompareListModelAttribute(mav, modelName, expectedList, comparator) | Sorts both lists using the comparator and compares them |
| assertAndReturnModelAttributeOfType(mav, modelName, expectedType) | Verifies the attribute exists, matches the expected type, and returns the cast value |

These methods take ModelAndView as the first parameter. Example:

~~~java
ModelAndViewAssert.assertViewName(mav, "books/list");
ModelAndViewAssert.assertModelAttributeAvailable(mav, "books");
ModelAndViewAssert.assertModelAttributeValue(
        mav, "pageTitle", "Books");
~~~

When an assertion fails, the assert* methods throw AssertionError, causing the test to fail in any test framework that recognizes assertion failures.

## 3. Adding the Spring Test dependency

ModelAndViewAssert resides in the spring-test module. In Spring Boot projects, the dependency is typically already supplied through the test starter:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

In Spring Framework projects not using Spring Boot, you can declare spring-test in test scope and add JUnit or the test framework your project uses:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

Use a spring-test version compatible with your application's Spring Framework version. Spring Boot projects should rely on Spring Boot's dependency management so Spring modules share aligned versions.

Import the assertion class:

~~~java
import org.springframework.test.web.ModelAndViewAssert;
~~~

## 4. Example of a controller returning ModelAndView

Suppose the application has a book listing page. The controller fetches the list from a service, puts data into the model, and selects the books/list view.

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping("/books")
    public ModelAndView listBooks() {
        ModelAndView mav = new ModelAndView("books/list");
        mav.addObject("pageTitle", "Books");
        mav.addObject("books", bookService.findAll());
        return mav;
    }
}
~~~

The service can return a list of DTOs:

~~~java
public interface BookService {
    List<BookSummary> findAll();
}

public record BookSummary(
        Long id,
        String title,
        String author) {
}
~~~

The controller's contract in this example includes:

- When the client sends GET /books, the controller chooses the logical view books/list.
- The model has a pageTitle attribute with the value Books.
- The model has a books attribute containing the list of books returned by the service.

These outcomes can be verified from the ModelAndView returned by the controller.

## 5. Testing a controller method directly

If the goal is to test the logic that builds the ModelAndView, you can invoke the controller method directly in a unit test. The service is replaced with a mock to control the controller's input data.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.BDDMockito.given;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.ModelAndViewAssert;
import org.springframework.web.servlet.ModelAndView;

class BookControllerUnitTest {

    private final BookService bookService =
            org.mockito.Mockito.mock(BookService.class);

    private final BookController controller =
            new BookController(bookService);

    @Test
    void returnsBookListViewWithPageTitleAndBooks() {
        List<BookSummary> books = List.of(
                new BookSummary(1L, "Spring in Action", "Craig Walls"),
                new BookSummary(2L, "Effective Java", "Joshua Bloch")
        );

        given(bookService.findAll()).willReturn(books);

        ModelAndView mav = controller.listBooks();

        assertNotNull(mav);

        ModelAndViewAssert.assertViewName(mav, "books/list");
        ModelAndViewAssert.assertModelAttributeValue(
                mav, "pageTitle", "Books");
        ModelAndViewAssert.assertModelAttributeAvailable(
                mav, "books");

        assertEquals(books, mav.getModel().get("books"));
    }
}
~~~

This test invokes the public method listBooks() and checks the resulting ModelAndView. It verifies that the controller sets the right view name and places the required data in the model.

The test scope has clear boundaries: it does not run the Spring MVC dispatcher, and does not check URL mappings, request binding, interceptors, filters, or the view resolver. If those behaviors are also part of the goal, use MockMvc.

You can use MockitoExtension and @Mock to manage mocks if the project already uses that extension. The example above creates the mock directly to emphasize that the controller is called like a regular Java object.

## 6. Using ModelAndViewAssert with MockMvc

MockMvc dispatches requests through the Spring MVC test infrastructure. After the request is processed, MvcResult provides the ModelAndView when the request follows a view-returning flow.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.ModelAndViewAssert;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.servlet.ModelAndView;

@WebMvcTest(BookController.class)
class BookControllerMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private BookService bookService;

    @Test
    void returnsBookListViewAndModel() throws Exception {
        List<BookSummary> books = List.of(
                new BookSummary(1L, "Spring in Action", "Craig Walls")
        );

        given(bookService.findAll()).willReturn(books);

        MvcResult result = mockMvc.perform(get("/books"))
                .andExpect(status().isOk())
                .andReturn();

        ModelAndView mav = result.getModelAndView();
        assertNotNull(mav);

        ModelAndViewAssert.assertViewName(mav, "books/list");
        ModelAndViewAssert.assertModelAttributeValue(
                mav, "pageTitle", "Books");
        ModelAndViewAssert.assertModelAttributeAvailable(
                mav, "books");
        ModelAndViewAssert.assertCompareListModelAttribute(
                mav, "books", books);
    }
}
~~~

The test flow consists of:

1. MockMvc sends GET /books.
2. Spring MVC resolves the handler for the request and invokes the controller.
3. Controller calls BookService, which has been replaced by a mock.
4. Controller returns ModelAndView.
5. MvcResult.getModelAndView() retrieves the resulting object.
6. ModelAndViewAssert verifies the view name and model attributes.

@WebMvcTest narrows the ApplicationContext to the MVC components needed for controller tests. @MockitoBean registers a mock in place of the BookService bean in the context. @MockitoBean is available in Spring Framework 6.2 and later; older Spring Boot versions may use Spring Boot's @MockBean.

If a controller uses @ResponseBody or returns ResponseEntity, getModelAndView() typically returns null because the request does not produce a view. In that case, inspect the response body using the corresponding result matchers.

## 7. Key assertions

### Verifying the view name with assertViewName

~~~java
ModelAndViewAssert.assertViewName(mav, "books/list");
~~~

This method compares the view name in ModelAndView with the expected name. It is useful when a controller has multiple branches returning different views.

For example, if the user is not logged in, the controller might return redirect:/login; a test for that branch can verify the redirect view name per contract.

The compared view name is the logical name inside ModelAndView, not the template file path after view resolver processing.

### Verifying a model attribute exists

~~~java
ModelAndViewAssert.assertModelAttributeAvailable(mav, "books");
~~~

This assertion confirms that the model contains the books key. It works well when you only need to guarantee that the data was placed in the model while detailed contents are verified in other assertions.

An attribute that exists with a null value can still differ from an attribute that is completely absent. If you need to check the value as well, use assertModelAttributeValue or retrieve the attribute by its expected type.

### Verifying a model attribute value

~~~java
ModelAndViewAssert.assertModelAttributeValue(
        mav, "pageTitle", "Books");
~~~

This method compares the expected value with the model value using object equality rules. Therefore, for DTOs or entities, the result depends on how the data type implements equals().

This assertion fits strings, numbers, enums, value objects, or types with clear equality semantics.

### Verifying multiple attributes with a Map

When checking several attributes at once, you can build an expected map:

~~~java
Map<String, Object> expectedModel = Map.of(
        "pageTitle", "Books",
        "pageSize", 20
);

ModelAndViewAssert.assertModelAttributeValues(
        mav, expectedModel);
~~~

This assertion confirms that all name/value pairs in expectedModel are present and equal in the model. It does not require the model to contain only those keys; the model may contain additional attributes.

If you need to assert that an attribute is absent, check explicitly with mav.getModel().containsKey("attributeName") or an appropriate assertion.

### Comparing lists in order

If element ordering is part of the display contract, use:

~~~java
ModelAndViewAssert.assertCompareListModelAttribute(
        mav, "books", expectedBooks);
~~~

This method compares each element of the list in the model without sorting either list first. Order therefore matters.

For instance, a listing page may require showing the newest books first. The test can verify that the list in the model is in the expected order.

Elements should have proper equality. For Java records, equality is generated automatically from the record components. For ordinary classes, you may need to implement equals() and hashCode().

### Comparing lists after sorting

If the contract only specifies the set of elements without dictating order, you can use:

~~~java
ModelAndViewAssert.assertSortAndCompareListModelAttribute(
        mav, "books", expectedBooks, comparator);
~~~

This method sorts both the model list and the expected list with the comparator and then compares element by element. If null is passed as the comparator, the API uses the natural ordering of the elements; the element type must implement Comparable.

Example comparator by ID:

~~~java
Comparator<BookSummary> byId =
        Comparator.comparing(BookSummary::id);

ModelAndViewAssert.assertSortAndCompareListModelAttribute(
        mav, "books", expectedBooks, byId);
~~~

Only ignore ordering when order truly is not part of the contract. If users expect results sorted by title or time, verify that exact ordering instead of re-sorting before comparing.

### Retrieving a model attribute and verifying its type

When you need to inspect an object in the model further, use:

~~~java
List<?> books =
        ModelAndViewAssert.assertAndReturnModelAttributeOfType(
                mav, "books", List.class);
~~~

This method confirms that the attribute exists and that its runtime type is compatible with the expected type, then returns the cast value. Because of Java generics type erasure, passing List.class only verifies that the object is a List; it does not verify the inner element type.

For example, you can combine it with AssertJ to check specific fields:

~~~java
List<?> books =
        ModelAndViewAssert.assertAndReturnModelAttributeOfType(
                mav, "books", List.class);

assertThat(books)
        .hasSize(2)
        .extracting("title")
        .containsExactly("Spring in Action", "Effective Java");
~~~

## 8. Distinguishing ModelAndView testing from rendered HTML testing

ModelAndViewAssert checks the data driving the view: the view name and the model. It does not prove that the final HTML output rendered correctly.

There are three distinct questions:

| Question | Suitable check |
|---|---|
| Which logical view did the controller pick? | ModelAndViewAssert.assertViewName or view().name(...) |
| What data did the controller place in the model? | ModelAndViewAssert or model().attribute(...) |
| What HTML do the view resolver and template produce? | Check response content in an MVC test or integration test with a view engine |

For example, a controller may return the right books/list name and the model may have the right list, yet the template could still reference a wrong property name or fail to render the data. Model assertions do not catch that HTML error.

If you need to verify response content:

~~~java
mockMvc.perform(get("/books"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("Spring in Action")));
~~~

To test templates meaningfully, the test needs the view engine and corresponding templates on the test/application classpath. When the goal is only how the controller picks a view and prepares the model, there is no need to turn the test into a full UI test.

## 9. Comparison with MockMvc result matchers

In tests using MockMvc, Spring provides result matchers to verify the view and model directly:

~~~java
mockMvc.perform(get("/books"))
        .andExpect(status().isOk())
        .andExpect(view().name("books/list"))
        .andExpect(model().attributeExists("books"))
        .andExpect(model().attribute("pageTitle", "Books"));
~~~

Common matchers:

- view().name(...) checks the view name.
- model().attributeExists(...) checks that model attributes exist.
- model().attribute(...) checks attribute values.
- model().attributeDoesNotExist(...) checks that attributes do not exist.
- model().attributeHasErrors(...) and related matchers check binding/validation errors.

You can use result matchers directly when the test only needs to verify view and model. ModelAndViewAssert fits when you have already extracted a ModelAndView, such as from MvcResult, or when calling controller methods directly in unit tests.

Current Spring API documentation describes ModelAndViewAssert as an assertion utility oriented toward JUnit 4 and TestNG scenarios. Its methods throw AssertionError, so they can be called in JUnit Jupiter tests and failures still fail the test; however, for new MVC tests written with Jupiter, result matchers usually fit more naturally into the MockMvc.perform(...).andExpect(...) chain.

## 10. Handling redirects and forwards

A controller returning ModelAndView can pick special view names:

~~~java
return new ModelAndView("redirect:/books");
~~~

Or:

~~~java
return new ModelAndView("forward:/login");
~~~

If the test inspects ModelAndView directly, it can verify the view name:

~~~java
ModelAndViewAssert.assertViewName(mav, "redirect:/books");
~~~

When using MockMvc, redirects should usually be verified with redirect-specific result matchers:

~~~java
mockMvc.perform(post("/books")
                .param("title", "Spring in Action"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/books"));
~~~

If the controller adds flash attributes via RedirectAttributes, check the flash map with an appropriate matcher, such as flash().attribute("message", "Book created"). Flash attributes have their own lifecycle across a redirect; do not assume they are part of the destination page's model.

## 11. When ModelAndView uses a View object

ModelAndView can be constructed with a view name:

~~~java
ModelAndView mav = new ModelAndView("books/list");
~~~

Or with a View object:

~~~java
ModelAndView mav = new ModelAndView(customView);
~~~

In the second case, mav.getView() returns the view object and mav.getViewName() can be null. assertViewName is only appropriate when the controller supplies a view name.

If the contract requires a specific view type, check the view object or verify the rendered output via an MVC test. Do not try to force a view object into a nonexistent logical name.

## 12. Common mistakes when using ModelAndViewAssert

### Passing arguments in the wrong order

Assertion methods take ModelAndView first, followed by the model attribute name and expected value:

~~~java
ModelAndViewAssert.assertModelAttributeValue(
        mav, "pageTitle", "Books");
~~~

Do not swap the order to put the attribute name before mav.

### Calling assertViewName on a response-body controller

If a controller uses @ResponseBody or returns ResponseEntity, the request does not produce a view. MvcResult.getModelAndView() may be null. Verify status, headers, and body instead of calling ModelAndViewAssert.

### Confusing view names with template paths

books/list is usually a logical view name. The template file path might be templates/books/list.html. Assert the exact value returned by the controller unless the goal is to test the view resolver.

### Checking only that an attribute exists

assertModelAttributeAvailable does not verify the attribute's contents. If the data must match expectations, use assertModelAttributeValue, list assertions, or retrieve the typed object and check its fields.

### Comparing objects without proper equality

assertModelAttributeValue and comparison assertions rely on element equality. If a DTO does not implement equals() as expected, two objects with identical data may still fail equality checks. Use records, implement proper equality, or check individual fields.

### Assuming the model must contain an exact key count

assertModelAttributeValues checks that the expected attributes are present and equal to the given values. It does not assert that the model contains only the keys in the map. If you want to check for extra keys, assert the model's size or key set separately.

### Assuming model assertions test the template

A valid model only proves the controller supplied the right data. The template itself can still be broken. When needed, inspect the rendered response content or integrate the view engine.

### Using ModelAndViewAssert for every controller type

Controllers returning JSON, file downloads, or ResponseEntity follow a different contract from view-returning controllers. Choose assertions matching the endpoint's response type.

## 13. Workflow for writing tests for view-returning controllers

You can follow this sequence:

1. **Identify the logical view:** read the controller branch and determine the view name a valid request should return.
2. **List model attributes:** identify the keys and data the template requires.
3. **Prepare collaborators:** mock services to return controlled data.
4. **Choose test scope:** call the controller directly if only testing ModelAndView construction; use MockMvc if testing URL mappings, request handling, and Spring MVC dispatch.
5. **Verify the view:** use assertViewName or view().name(...).
6. **Verify the model:** check key presence, exact values, or ordered lists.
7. **Verify rendering when needed:** inspect response content or run tests with a view engine.
8. **Test other branches:** error views, redirects, model validation errors, or empty data if they belong to the requirements.

A clear test name such as returnsBookListViewWithPageTitleAndBooks communicates both the condition and outcome. When the test fails, the assertion pinpoints which view name or model attribute failed.

## 14. Example testing model validation errors

A view-returning controller can accept a form object and return to the input page when data is invalid:

~~~java
@PostMapping("/books")
public ModelAndView createBook(
        @Valid @ModelAttribute("bookForm") BookForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        ModelAndView mav = new ModelAndView("books/new");
        mav.addObject("pageTitle", "Create book");
        return mav;
    }

    bookService.create(form);
    return new ModelAndView("redirect:/books");
}
~~~

For the validation-error branch, you can verify the view and required model attributes:

~~~java
ModelAndView mav = controller.createBook(invalidForm, bindingResult);

ModelAndViewAssert.assertViewName(mav, "books/new");
ModelAndViewAssert.assertModelAttributeAvailable(mav, "bookForm");
ModelAndViewAssert.assertModelAttributeValue(
        mav, "pageTitle", "Create book");
~~~

If you want to verify binding error details, retrieve BindingResult from the model under its key or use MockMvc with model().attributeHasErrors("bookForm"). When testing through MVC, send actual request parameters so Spring performs binding and validation.

## 15. Checklist when reviewing a test using ModelAndViewAssert

- The ModelAndView object comes from the exact controller or request under test.
- The view name is the logical name per contract.
- Required model attributes are present.
- Model values are compared using appropriate equality semantics.
- Lists are verified in order when order is meaningful.
- Do not assume ModelAndViewAssert verified HTML rendering.
- Controllers returning JSON or response bodies are verified with HTTP response assertions.
- Tests use MockMvc when Spring MVC dispatch and request mapping must be verified.
- Tests check view resolvers/templates when that is the actual target.

## References

- [Spring Framework API: ModelAndViewAssert](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/ModelAndViewAssert.html)
- [Spring Framework API: ModelAndView](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/ModelAndView.html)
- [Spring Framework Reference: Testing Spring MVC Controllers](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)

## Conclusion

ModelAndViewAssert helps verify what a controller returns to the view layer: the logical view name and model attributes. You can use it with a ModelAndView obtained directly from a controller or from MockMvc's MvcResult. When you need to test request mapping and MVC dispatch, MockMvc is the right boundary; when you need to test final HTML output, inspect the rendered response or view engine configuration. Choosing assertions aligned with the controller's contract keeps tests clear and maintainable.
