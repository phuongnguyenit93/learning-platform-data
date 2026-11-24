# Model, View Name, and ModelAndView

In Spring MVC, a controller can return data for a view to render into a web page. Three concepts commonly appear together: **model**, **view name**, and **`ModelAndView`**. The model holds the data the view needs; the view name identifies the logical view for Spring to resolve; `ModelAndView` is an object that can carry both the model and view information in a single return value.

When testing with `MockMvc`, you can verify that a controller populated the right data in the model and chose the right view without sending HTTP requests over the network. Matchers such as `model()`, `view()`, `forwardedUrl()`, and `redirectedUrl()` clearly express the MVC outcomes the controller commits to.

## 1. Model in Spring MVC

The model is a collection of named attributes used by a view when rendering a response. For example, a product detail page may need the product object, a page title, and a list of categories:

```java
model.addAttribute("product", product);
model.addAttribute("pageTitle", "Product detail");
model.addAttribute("categories", categories);
```

Attribute names serve as the keys by which the view accesses data. In JSP, data is typically read through expressions or tags; in Thymeleaf, a template can access an attribute using an expression like `${product.name}`.

In a controller, Spring provides a `Model` parameter for adding attributes:

```java
@Controller
class ProductPageController {
    @GetMapping("/products/{id}")
    String detail(@PathVariable long id, Model model) {
        Product product = new Product(id, "Notebook");
        model.addAttribute("product", product);
        model.addAttribute("pageTitle", "Product detail");
        return "products/detail";
    }
}
```

`Model` is the abstraction controllers should generally use. Spring also provides `ModelMap`, a map type with convenience methods for adding attributes. Either can be used as a handler method parameter:

```java
@GetMapping("/products")
String list(ModelMap model) {
    model.addAttribute("products", List.of(
            new Product(1L, "Notebook"),
            new Product(2L, "Pen")));
    return "products/list";
}
```

In normal cases you do not instantiate a model manually and pass it to a view. Spring MVC prepares the model for the handler and collects the attributes the controller adds.

### Adding and Reading Model Attributes

Common `Model` operations include:

| Method | Purpose |
| --- | --- |
| `addAttribute(name, value)` | Adds an attribute with an explicit name |
| `addAttribute(value)` | Adds an attribute and lets Spring infer the name from the object's type |
| `addAllAttributes(map)` | Adds attributes from a map |
| `mergeAttributes(map)` | Adds attributes without overwriting existing keys |
| `containsAttribute(name)` | Checks whether an attribute exists |
| `asMap()` | Retrieves a map of the current attributes |

In application code, assign explicit names to key view attributes:

```java
model.addAttribute("product", product);
```

Relying on class-inferred names can be convenient in simple cases, but explicit names make templates and tests easier to read and avoid surprises if object types or naming conventions change.

## 2. What Is a View Name?

A view name is the logical name returned by a controller so Spring can locate the component that renders the response. For example:

```java
return "products/detail";
```

The string `products/detail` is usually not a browser URL, nor is it necessarily a full file path. It is a name passed to a `ViewResolver`. The view resolver uses its configuration to locate the corresponding `View` object.

With an `InternalResourceViewResolver` for JSP, configuration might add a prefix and suffix:

```java
@Bean
InternalResourceViewResolver viewResolver() {
    InternalResourceViewResolver resolver = new InternalResourceViewResolver();
    resolver.setPrefix("/WEB-INF/views/");
    resolver.setSuffix(".jsp");
    return resolver;
}
```

When the controller returns `products/detail`, the resolver can map it to `/WEB-INF/views/products/detail.jsp`. With Thymeleaf, the view name can be mapped to the corresponding template in the configured template directory.

Key points to remember:

- The controller chooses the logical view name.
- `ViewResolver` determines the corresponding view implementation or template.
- The view receives the model and produces the response body using the configured rendering technology.
- Template paths do not necessarily match request URLs.

Therefore, asserting `view().name("products/detail")` verifies that the controller chose the right logical view. It does not by itself prove that the JSP/Thymeleaf file exists or renders without errors.

## 3. Distinguishing `Model`, `ModelMap`, and `ModelAndView`

These three types are related but serve different handler styles:

| Type | Role | Typical Usage |
| --- | --- | --- |
| `Model` | Abstraction for controllers to add data for the view | Accepted as a parameter, then return the view name as a `String` |
| `ModelMap` | Map of model attributes with convenience APIs | Accepted as a parameter when map-style operations are needed |
| `ModelAndView` | Bundles both view information and the model in the return value | Instantiate, populate the model, and return from the handler |

Example using `Model` and returning a view name:

```java
@GetMapping("/products/{id}")
String detail(@PathVariable long id, Model model) {
    model.addAttribute("product", findProduct(id));
    return "products/detail";
}
```

Example using `ModelAndView`:

```java
@GetMapping("/products/{id}")
ModelAndView detail(@PathVariable long id) {
    ModelAndView result = new ModelAndView("products/detail");
    result.addObject("product", findProduct(id));
    return result;
}
```

Both approaches can express the same MVC outcome. Using `Model` is usually simpler when the view name is a string returned by the handler. `ModelAndView` is useful when you want to construct or pass along a result that already encapsulates both view and model, or when a component's API works directly with that object.

## 4. Creating and Using `ModelAndView`

`ModelAndView` belongs to `org.springframework.web.servlet`. It holds view information and model attributes. It can be constructed in several ways:

```java
ModelAndView first = new ModelAndView("products/detail");

ModelAndView second = new ModelAndView(
        "products/detail", "product", product);

ModelAndView third = new ModelAndView(
        "products/detail", Map.of("product", product));
```

Commonly used operations:

| Method | Purpose |
| --- | --- |
| `setViewName(name)` | Sets the logical view name |
| `getViewName()` | Gets the logical view name if set by name |
| `setView(view)` | Sets a `View` object directly |
| `getView()` | Gets the `View` object if present |
| `addObject(name, value)` | Adds an attribute to the model |
| `addAllObjects(map)` | Adds multiple attributes |
| `getModel()` | Gets the model as a `Map` |
| `getModelMap()` | Gets the model as a `ModelMap` |
| `hasView()` | Checks whether a view name or view instance has been set |
| `isReference()` | Checks whether the view is represented by a reference name or a `View` instance |

Full example:

```java
@GetMapping("/products")
ModelAndView list() {
    ModelAndView result = new ModelAndView();
    result.setViewName("products/list");
    result.addObject("pageTitle", "Product catalog");
    result.addObject("products", productService.findAll());
    return result;
}
```

You can set a `View` instance directly instead of a view name. In that case Spring does not need to resolve a view name in the same way:

```java
ModelAndView result = new ModelAndView(viewInstance);
result.addObject("product", product);
return result;
```

This is less common in ordinary controllers, but can be useful when the view has already been created or selected by another component.

## 5. When Is a Return Value Treated as a View Name?

The semantics of a return type depend on annotations and how Spring MVC handles the handler method.

| Controller/Return Type | Typical Meaning |
| --- | --- |
| `@Controller` returning `String` | Logical view name |
| `@Controller` taking `Model`, returning `String` | Logical view name; model is used for the view |
| `@Controller` returning `ModelAndView` | View together with model |
| `@ResponseBody` returning object or `String` | Response body data, not a view name |
| `@RestController` returning object or `String` | Response body because `@RestController` includes `@ResponseBody` |
| Returning `ResponseEntity<T>` | HTTP status, headers, and body |

Example showing the difference between an MVC view and a REST response:

```java
@Controller
class PageController {
    @GetMapping("/welcome")
    String welcome(Model model) {
        model.addAttribute("message", "Welcome");
        return "welcome";
    }
}

@RestController
class ApiController {
    @GetMapping("/api/welcome")
    String welcome() {
        return "Welcome";
    }
}
```

In the first controller, `welcome` is a view name. In the second controller, the string `Welcome` is written to the response body. Do not use `view().name(...)` matchers for REST endpoints returning JSON or text bodies; use body matchers such as `content()` or `jsonPath()`.

Other return types such as `void`, `null`, `Map`, `@ModelAttribute`, or `View` have their own handling rules and may depend on default configuration. When you want an explicit contract, return a view name or `ModelAndView` explicitly for MVC pages; for REST endpoints, declare `@ResponseBody` explicitly or use `@RestController`.

## 6. Populating Model Data with `@ModelAttribute`

`@ModelAttribute` can be placed on a method to add shared data to the model before handlers are invoked:

```java
@Controller
class ProductPageController {
    @ModelAttribute("pageTitle")
    String pageTitle() {
        return "Product catalog";
    }

    @GetMapping("/products")
    String list(Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }
}
```

The `pageTitle` attribute can appear in the model of matching handlers in the controller. This is convenient for shared data such as menu items or page titles. Avoid putting heavy service-lookup logic inside `@ModelAttribute` methods if not every request needs that data.

`@ModelAttribute` on a parameter can also bind request parameters into a form object:

```java
@PostMapping("/products/search")
String search(@ModelAttribute ProductSearchForm form, Model model) {
    model.addAttribute("products", productService.search(form));
    return "products/list";
}
```

If the form has validation, you can place `@Valid` and `BindingResult` immediately after the validated parameter:

```java
@PostMapping("/products")
String create(@Valid @ModelAttribute("form") ProductForm form,
              BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "products/new";
    }
    productService.create(form);
    return "redirect:/products";
}
```

When validation errors occur, the model typically contains the form object and its corresponding binding result. Tests can verify the returned view, the form attribute, and field errors using `model()` matchers.

## 7. View Names, Redirects, and Forwards

In addition to regular view names, Spring MVC supports special prefixes to request a redirect or forward:

```java
return "redirect:/products";
```

`redirect:` generates a redirect response to the target URL. The browser or HTTP client can then send the next request to that URL. This is commonly used to implement Post/Redirect/Get to avoid resubmitting forms when users refresh the page.

```java
return "forward:/products";
```

`forward:` instructs the servlet container to forward the request internally to the target path within the same server request. Forwarding does not create a new HTTP redirect, and the client-side URL does not necessarily change.

| Outcome | Behavior | MockMvc Matcher |
| --- | --- | --- |
| Regular view | Selects a view to render | `view().name("products/list")` |
| Redirect | Response redirects to another URL | `redirectedUrl("/products")` |
| Forward | Servlet forwards request internally | `forwardedUrl("/products")` |

Do not confuse a view name with a URL. `products/detail` can be a logical view name mapped by a resolver to a template file; `redirect:/products` is an instruction to redirect to a URL; `forward:/products` is an instruction to forward internally.

## 8. RedirectAttributes and Flash Attributes

When redirecting after form submission, you may need to pass a message to the next request. `RedirectAttributes` supports two kinds of data:

- `addAttribute(name, value)` adds an attribute that can be placed into the redirect URL, typically as a path variable or query parameter.
- `addFlashAttribute(name, value)` stores flash data so the next request can read it; flash data is typically held in the session across the redirect and then consumed.

Example:

```java
@PostMapping("/products")
String create(@RequestParam String name, RedirectAttributes attributes) {
    productService.create(name);
    attributes.addAttribute("source", "form");
    attributes.addFlashAttribute("notice", "Product created");
    return "redirect:/products";
}
```

The redirect URL can carry the query parameter `source=form`; the `notice` message is sent as a flash attribute for the next request. Do not put sensitive data or large objects into query parameters because URLs can appear in browser history, access logs, and referrers.

In MockMvc, you can assert the redirect URL and flash attributes directly on the POST request result:

```java
mockMvc.perform(post("/products").param("name", "Notebook"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/products?source=form"))
        .andExpect(flash().attribute("notice", "Product created"));
```

If a test also needs to verify the subsequent GET request, you can extract the flash attributes from the POST result and attach them to the next request via `.flashAttrs(...)`. This confirms the target page receives the notification after the redirect.

## 9. Testing Model and View with MockMvc

Spring Test provides matchers in `MockMvcResultMatchers` to verify the model and view. The following example uses `standaloneSetup` to focus on controller behavior:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.servlet.ModelAndView;

import java.util.List;

record Product(long id, String name) {
}

@Controller
class CatalogPageController {
    @GetMapping("/catalog/products/{id}")
    String detail(@PathVariable long id, Model model) {
        model.addAttribute("product", new Product(id, "Notebook"));
        model.addAttribute("pageTitle", "Product detail");
        return "catalog/detail";
    }

    @GetMapping("/catalog/products")
    ModelAndView list() {
        ModelAndView result = new ModelAndView("catalog/list");
        result.addObject("products", List.of(
                new Product(1L, "Notebook"),
                new Product(2L, "Pen")));
        return result;
    }
}
```

Test verifying the handler using `Model`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

class CatalogPageControllerTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new CatalogPageController())
                .build();
    }

    @Test
    void returnsDetailViewWithProductInModel() throws Exception {
        mockMvc.perform(get("/catalog/products/{id}", 7))
                .andExpect(status().isOk())
                .andExpect(view().name("catalog/detail"))
                .andExpect(model().attributeExists("product"))
                .andExpect(model().attribute("product", new Product(7, "Notebook")))
                .andExpect(model().attribute("pageTitle", "Product detail"));
    }
}
```

Test verifying the handler returning `ModelAndView`:

```java
@Test
void returnsListViewWithProductsInModel() throws Exception {
    mockMvc.perform(get("/catalog/products"))
            .andExpect(status().isOk())
            .andExpect(view().name("catalog/list"))
            .andExpect(model().attributeExists("products"))
            .andExpect(model().attribute("products", List.of(
                    new Product(1L, "Notebook"),
                    new Product(2L, "Pen"))));
}
```

Both tests above verify processing results at the Spring MVC layer. `standaloneSetup` does not load the full application context and suits simple controllers. When the goal is to test view resolver configuration, interceptors, controller advice, or real MVC beans, use `webAppContextSetup(webApplicationContext)` or `@WebMvcTest`/`@SpringBootTest` depending on the required scope.

## 10. Common Model and View Matchers

`model()` returns matchers to verify the model created during request processing:

| Matcher | Purpose |
| --- | --- |
| `model().attributeExists("product")` | Checks that the attribute exists |
| `model().attributeDoesNotExist("error")` | Checks that the attribute does not exist |
| `model().attribute("pageTitle", "Products")` | Checks the attribute value |
| `model().attributeHasErrors("form")` | Checks that the object has binding/validation errors |
| `model().attributeHasNoErrors("form")` | Checks that the object has no errors |
| `model().attributeErrorCount("form", 2)` | Checks the total error count |
| `model().attributeHasFieldErrors("form", "name")` | Checks that a field has errors |
| `model().size(3)` | Checks the number of model attributes |

`view()` checks the selected view:

```java
mockMvc.perform(get("/catalog/products"))
        .andExpect(view().name("catalog/list"));
```

If the controller uses redirect or forward, use the corresponding matcher:

```java
mockMvc.perform(post("/catalog/products").param("name", "Pen"))
        .andExpect(redirectedUrl("/catalog/products"));

mockMvc.perform(get("/catalog/legacy-products"))
        .andExpect(forwardedUrl("/catalog/products"));
```

Matcher names are statically imported from `MockMvcResultMatchers`. Using the matcher tailored to each outcome type expresses test intent more clearly than checking only the response body.

## 11. Inspecting ModelAndView Directly via MvcResult

When you need to check multiple attributes or inspect `ModelAndView` metadata, you can retrieve `MvcResult` via `andReturn()`:

```java
MvcResult result = mockMvc.perform(get("/catalog/products"))
        .andExpect(status().isOk())
        .andReturn();

ModelAndView modelAndView = result.getModelAndView();

assertThat(modelAndView).isNotNull();
assertThat(modelAndView.getViewName()).isEqualTo("catalog/list");
assertThat(modelAndView.getModel()).containsKey("products");
```

`MvcResult.getModelAndView()` can be `null` for requests that do not produce a view/model outcome, such as REST endpoints returning a response body. Therefore, only use this API when testing an MVC view flow. For REST endpoints, use `getResponse()` and appropriate body/header/status matchers.

Usually, `view()` and `model()` matchers are concise and readable. `MvcResult` is appropriate when complex assertion logic is needed or when passing results to a subsequent check.

## 12. Verifying Validation Errors in the Model

With MVC forms, a controller can return the same view when input data is invalid. Tests should verify the view name, form object, and validation errors:

```java
@PostMapping("/catalog/products")
String save(@Valid @ModelAttribute("form") ProductForm form,
            BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "catalog/new";
    }
    return "redirect:/catalog/products";
}
```

Test example:

```java
mockMvc.perform(post("/catalog/products")
                .param("name", "")
                .param("price", "-1"))
        .andExpect(status().isOk())
        .andExpect(view().name("catalog/new"))
        .andExpect(model().attributeExists("form"))
        .andExpect(model().attributeHasErrors("form"))
        .andExpect(model().attributeHasFieldErrors("form", "name"));
```

For the test to work, `ProductForm` must declare appropriate constraints such as `@NotBlank` or `@Positive`, and a validation provider must be on the test runtime classpath. The `BindingResult` parameter must immediately follow the validated object so the controller can handle binding/validation errors. Without `BindingResult` in the proper position, an exception may be passed to an exception resolver instead of entering the controller's error-handling branch.

## 13. Verifying a View Name Is Not Template Rendering

`MockMvc` can verify that a controller selects the right view name and supplies the corresponding model. However, how much template verification occurs depends on the view technology and loaded configuration.

- With `standaloneSetup`, tests usually focus on the handler, model, and logical view name. Without configuring a view resolver or view implementation, the test does not verify the actual template.
- With `webAppContextSetup`, the view resolver and view beans loaded in the context can participate in rendering the response.
- JSP typically requires a servlet container capable of compiling and executing JSPs; `MockServletContext` does not fully replace a JSP deployment environment.
- Thymeleaf or other template engines can render during tests if the required dependencies, template resolver, and configuration are loaded.

If the goal is just to confirm the controller returns `catalog/detail` with `product`, `view()` and `model()` matchers are usually sufficient. If the goal is to verify the final HTML, configure the template engine in tests or run integration tests suited to the real rendering environment.

## 14. Common Mistakes When Testing Model and View

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| `view().name(...)` does not match | Controller returns a different view name or uses redirect/forward | Identify the exact outcome type returned by the handler and use the matching matcher |
| `model().attributeExists(...)` fails | Controller did not add the attribute or used a different attribute name | Check `addAttribute` and the name expected by the view |
| `getModelAndView()` returns `null` | Handler returns a response body or a non-view response | Use body/header/status matchers for REST endpoints |
| View name test passes but page fails to render | Template is missing or view resolver is misconfigured | Check template paths and resolver configuration; add rendering tests when needed |
| Returned string is treated as a response body | Handler uses `@ResponseBody` or `@RestController` | Use `@Controller` for views or assert the body as intended |
| Flash attribute does not appear in POST request model | Flash attributes are carried over to the next request | Check `flash()` or perform the redirected request with the flash map |
| Redirect test expects forward | Confused `redirect:` and `forward:` prefixes | Use `redirectedUrl` or `forwardedUrl` matching the actual behavior |
| Validation errors are missing from the model | Missing constraints, validation provider, or misplaced `BindingResult` | Check `@Valid`, validation dependencies, and parameter order |
| Model has unexpected extra attributes | `@ModelAttribute` methods or binding automatically added attributes | Check all controller advice/model initialization before asserting exact model size |

## 15. Principles for Writing MVC Result Assertions

1. Use `Model` when a handler needs to add data and return a logical view name as a `String`.
2. Use `ModelAndView` when you want to bundle view and model in a single return value.
3. Give model attributes clear names and assert those exact names in tests.
4. Distinguish logical view names from template file paths and browser URLs.
5. Use `view().name(...)` for regular views, `redirectedUrl(...)` for redirects, and `forwardedUrl(...)` for forwards.
6. Use `model()` to verify data, form objects, and validation errors supplied by the controller to the view.
7. Do not use view/model matchers for REST endpoints returning bodies; verify status, headers, and body instead.
8. Use `webAppContextSetup` or an appropriate test context when verifying real MVC configuration; use dedicated rendering tests when final HTML must be checked.

Model, view name, and `ModelAndView` make up key controller outputs in server-rendered Spring MVC applications. When tests assert both the logical view and required model attributes, selecting the wrong page or omitting data is caught directly at the MVC layer. Separating controller-outcome checks from template-rendering checks also clarifies which part of application behavior each test protects.
